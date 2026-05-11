import os
import httpx
import json
import asyncio
import psycopg2
import shutil
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# --- 1. 設定區 ---
HUME_API_KEY = "YRolQS4LUtijkq8V89lMsneS1PGgRZYdXlf3T64ELG73z1fa" 
BASE_PATH = Path(r"D:\工作\CODE\python\Moodanaly-project")
IMAGE_DIR = BASE_PATH / "testhumiai"
RESULT_DIR = IMAGE_DIR / "result"
BATCH_URL = "https://api.hume.ai/v0/batch/jobs" 

# PostgreSQL 設定
DB_CONFIG = {
    "dbname": "Moodanaly-project",
    "user": "postgres",
    "password": "0",
    "host": "127.0.0.1",
    "port": "5432"
}

# 確保目錄存在
IMAGE_DIR.mkdir(parents=True, exist_ok=True)
RESULT_DIR.mkdir(parents=True, exist_ok=True)

# CORS 設定：允許手機 ngrok 請求[cite: 1]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 掛載靜態檔案
app.mount("/images", StaticFiles(directory=str(IMAGE_DIR)), name="images")

# --- 2. 資料庫核心函式 ---

def save_to_postgres(test_id, emotions_dict):
    """
    將結果寫入 PostgreSQL
    :param emotions_dict: 傳入格式為 {'Interest': 0.54, 'Calmness': 0.42}
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        # 存入 test_name 與 JSON 格式的字典
        query = "INSERT INTO emotion_logs (test_name, detected_emotions) VALUES (%s, %s)"
        cur.execute(query, (test_id, json.dumps(emotions_dict)))
        
        conn.commit()
        
        # 除錯用：印出當前筆數確認真的有存入
        cur.execute("SELECT COUNT(*) FROM emotion_logs;")
        count = cur.fetchone()[0]
        
        cur.close()
        conn.close()
        print(f"🗄️ 資料庫已更新！總筆數: {count}")
    except Exception as e:
        print(f"❌ 資料庫寫入失敗: {e}")

# --- 3. 核心邏輯區 ---

async def process_hume_ai(file_path, test_id):
    """分析情緒並過濾前五名 > 40% 的結果"""
    async with httpx.AsyncClient(timeout=None) as client:
        # A. 建立 Hume AI 任務
        headers = {"X-Hume-Api-Key": HUME_API_KEY}
        payload = {"models": {"face": {}}}
        
        with open(file_path, "rb") as f:
            upload_files = [("file", ("image.jpg", f, "image/jpeg"))]
            response = await client.post(
                BATCH_URL, 
                headers=headers, 
                data={"json": json.dumps(payload)}, 
                files=upload_files
            )
        
        if response.status_code not in [200, 201]:
            print(f"❌ Hume 任務建立失敗: {response.text}")
            return

        job_id = response.json().get("job_id")
        
        # B. 輪詢狀態 (Polling)
        status_url = f"{BATCH_URL}/{job_id}"
        while True:
            res = await client.get(status_url, headers=headers)
            status = res.json().get("state", {}).get("status")
            if status == "COMPLETED": break
            if status in ["FAILED", "CANCELLED"]: return
            await asyncio.sleep(2) 

        # C. 解析結果
        pred_url = f"{BATCH_URL}/{job_id}/predictions"
        pred_res = await client.get(pred_url, headers={"X-Hume-Api-Key": HUME_API_KEY})
        if pred_res.status_code == 200:
            results = pred_res.json()
            emotions = results[0]["results"]["predictions"][0]["models"]["face"]["grouped_predictions"][0]["predictions"][0]["emotions"]
            
            # 1. 先取前五名
            sorted_all = sorted(emotions, key=lambda x: x['score'], reverse=True)
            top_five = sorted_all[:5]
            
            # 2. 檢查是否有超過 40% 的
            top_filtered = [e for e in top_five if e["score"] >= 0.4]

            if top_filtered:
                # 情況 A：有機率 > 40%，直接存入
                filtered_data = {e["name"]: round(e["score"], 4) for e in top_filtered}
                save_to_postgres(test_id, filtered_data)
                return {"status": "success", "action": "auto_saved", "data": filtered_data}
            else:
                # 情況 B：全都 < 40%，回傳前五名給前端讓使用者選
                options = {e["name"]: round(e["score"], 4) for e in top_five}
                return {"status": "low_confidence", "action": "user_selection_required", "options": options}



# --- 4. 路由區 ---

@app.post("/api/save_manual")
async def save_manual(
    test_id: str = Form(...), 
    selected_emotion: str = Form(...), 
    score: float = Form(...)
):
    """接收使用者從手機端手動選擇的情緒結果並存入資料庫"""
    try:
        # 將單一情緒與分數封裝成字典格式，以符合 JSONB 存儲規範
        manual_data = {selected_emotion: score}
        save_to_postgres(test_id, manual_data)
        return {"status": "success", "message": "手動選擇已存入資料庫"}
    except Exception as e:
        print(f"❌ 手動存檔路由發生錯誤: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/api/upload")
async def handle_upload(file: UploadFile = File(...), test_id: str = Form(...)):
    """修改為：等待分析完成後直接回傳結果，不再使用背景任務"""
    file_path = IMAGE_DIR / file.filename
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # 關鍵：直接 await 取得結果，這樣 result 才能回傳給前端
        result = await process_hume_ai(file_path, test_id)
        
        if result:
            return result
        else:
            return {"status": "error", "message": "分析失敗"}
            
    except Exception as e:
        print(f"❌ 處理失敗: {e}")
        return {"status": "error", "message": str(e)}

# process_hume_ai 函式內容保持你最後提供的版本即可

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)