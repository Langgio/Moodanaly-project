import os
import httpx
import json
import asyncio
import psycopg2
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# --- 設定區 ---
HUME_API_KEY = "YRolQS4LUtijkq8V89lMsneS1PGgRZYdXlf3T64ELG73z1fa"
BASE_PATH = Path(r"D:\工作\CODE\python\Moodanaly-project")
IMAGE_DIR = BASE_PATH / "testhumiai"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)
RESULT_DIR = IMAGE_DIR / "result"
BATCH_URL = "https://api.hume.ai/v1/batch/jobs"

# 資料庫連線設定 (請確認您的 PostgreSQL 資訊)
DB_CONFIG = {
    "dbname": "postgres", # 您的資料庫名稱
    "user": "s1122",      # 您的 User ID
    "password": "s1122",  # 您的 Password
    "host": "127.0.0.1",
    "port": "5432"
}

# 確保目錄存在
RESULT_DIR.mkdir(parents=True, exist_ok=True)

# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 掛載靜態圖片資料夾
app.mount("/images", StaticFiles(directory=str(IMAGE_DIR)), name="images")

# --- 路由區 ---

@app.get("/", response_class=HTMLResponse)
async def get_index():
    """回傳 LIFF 前端網頁，解決 Not Found 問題"""
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()
@app.get("/test2", response_class=HTMLResponse)
async def get_second_page():
    """當使用者進入 /test2 網址時"""
    with open("test2.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/api/upload")
async def handle_upload(file: UploadFile = File(...), test_id: str = Form(...)):
    # 建立完整的檔案存檔路徑
    file_path = IMAGE_DIR / file.filename
    
    try:
        # 使用 async 讀取檔案內容
        contents = await file.read()
        
        # 執行實體寫入
        with open(file_path, "wb") as f:
            f.write(contents)
        
        print(f"📸 照片已成功存檔至: {file_path}")
        
        # 執行後續的 Hume AI 分析流程[cite: 1]
        asyncio.create_task(process_hume_ai(file_path, test_id))
        
        return {"status": "success", "path": str(file_path)}
        
    except Exception as e:
        print(f"❌ 存檔失敗: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- 核心邏輯區 ---

async def process_hume_ai(file_path, test_id):
    async with httpx.AsyncClient(timeout=None) as client:
        # A. 建立 Hume AI 任務[cite: 3]
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
        
        # B. 等待結果完成 (輪詢)[cite: 3]
        status_url = f"{BATCH_URL}/{job_id}"
        while True:
            res = await client.get(status_url, headers=headers)
            status = res.json().get("state", {}).get("status")
            if status == "COMPLETED": break
            if status in ["FAILED", "CANCELLED"]: return
            await asyncio.sleep(2) # 圖片較快，間隔縮短

        # C. 下載預測結果[cite: 3]
        pred_url = f"{BATCH_URL}/{job_id}/predictions"
        pred_res = await client.get(pred_url, headers=headers)
        if pred_res.status_code == 200:
            results = pred_res.json()
            
            # 儲存 JSON 檔
            result_path = RESULT_DIR / f"{file_path.stem}_result.json"
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=4, ensure_ascii=False)

            # D. 解析情緒：取前五名，並判斷是否 > 40% (0.4)
            try:
                emotions = results[0]["results"]["predictions"][0]["models"]["face"]["grouped_predictions"][0]["predictions"][0]["emotions"]
                # 排序
                sorted_emotions = sorted(emotions, key=lambda x: x["score"], reverse=True)[:5]
                # 過濾超過 40%
                filtered = [e["name"] for e in sorted_emotions if e["score"] >= 0.4]
                
                if filtered:
                    save_to_postgres(test_id, filtered)
                    print(f"✅ {test_id} 辨識成功，存入情緒: {filtered}")
            except Exception as e:
                print(f"⚠️ 解析 JSON 失敗: {e}")

def save_to_postgres(test_id, emotions_list):
    """將結果寫入 PostgreSQL"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        # 假設您的 table 叫 emotion_logs，欄位有 test_name, detected_emotions
        cur.execute(
            "INSERT INTO emotion_logs (test_name, detected_emotions, created_at) VALUES (%s, %s, NOW())",
            (test_id, json.dumps(emotions_list))
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ 資料庫寫入失敗: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)