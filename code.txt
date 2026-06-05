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
from datetime import date

# 初始化 FastAPI 應用程式
app = FastAPI()

# --- 1. 設定區 (環境與路徑配置) ---

# Hume AI 官方 API 金鑰 (用於進行表情模型辨識)
HUME_API_KEY = "YRolQS4LUtijkq8V89lMsneS1PGgRZYdXlf3T64ELG73z1fa" 

# 【關鍵修改】動態獲取當前執行檔案的目錄，徹底解決實體絕對路徑寫死在特定電腦的問題
BASE_PATH = Path(__file__).parent.resolve()

# 根據專案根目錄動態串接圖片暫存與分析結果的資料夾路徑
IMAGE_DIR = BASE_PATH / "testhumiai"
RESULT_DIR = IMAGE_DIR / "result"

# Hume AI 批次處理工單 (Batch Jobs) 的官方 API 端點網址
BATCH_URL = "https://api.hume.ai/v0/batch/jobs" 
#                                 ↑
#  AI輸出hume.ai會改成https://api.hume.ai/v1/batch/jobs，要記得改回來

# PostgreSQL 本地資料庫連線參數設定
DB_CONFIG = {
    "dbname": "Moodanaly-project",  # 資料庫名稱
    "user": "postgres",             # 資料庫使用者帳號
    "password": "0",                # 資料庫密碼
    "host": "127.0.0.1",            # 本地端 IP
    "port": "5432"                  # PostgreSQL 預設埠號
}

# 自動檢查並建立執行所需的資料夾目錄，防止因找不到目錄引發讀寫異常
IMAGE_DIR.mkdir(parents=True, exist_ok=True)
RESULT_DIR.mkdir(parents=True, exist_ok=True)

# CORS 跨來源資源共用配置：允許手機端 ngrok 隧道進行跨網域 API 請求與資料存取 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 生產環境整合時可由組員限縮範圍，目前維持廣播允許測試 
    allow_credentials=True,
    allow_methods=["*"],  # 允許所有 HTTP 請求方法 (GET, POST 等) 
    allow_headers=["*"],  # 允許所有自訂或標準 HTTP 標頭
)

# 掛載靜態檔案目錄，允許前端透過 URL (例如 /images/xxx.jpg) 直接讀取上傳的暫存照片
app.mount("/images", StaticFiles(directory=str(IMAGE_DIR)), name="images")


# --- 2. 資料庫核心函式 ---

def save_to_postgres(test_id, emotions_dict):
    """
    將情緒分析結果包裝並寫入 PostgreSQL 資料庫
    :param test_id: 前端帶入的測試回合識別代碼 (例如 test 1)
    :param emotions_dict: 傳入格式為字典，例如 {'Joy': 0.854, 'Calmness': 0.421}
    """
    try:
        # 建立與資料庫的實體連線
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        # 執行 SQL 插入語法，將情緒字典物件轉為 JSON 字串存入 JSONB 欄位中
        query = "INSERT INTO emotion_logs (test_name, detected_emotions) VALUES (%s, %s)"
        cur.execute(query, (test_id, json.dumps(emotions_dict)))
        
        # 提交事務，確保資料實體寫入磁碟
        conn.commit()
        
        # 除錯與驗證：在伺服器後台印出目前總筆數，方便串接人員比對資料是否遺漏
        cur.execute("SELECT COUNT(*) FROM emotion_logs;")
        count = cur.fetchone()[0]
        
        # 釋放記憶體與關閉資料庫連線
        cur.close()
        conn.close()
        print(f"資料庫已更新！目前總筆數: {count}")
 
    except Exception as e:
        print(f"資料庫寫入失敗，請檢查資料表欄位或規格: {e}")


# --- 3. 核心商務邏輯區 ---

async def process_hume_ai(file_path, test_id):
    """
    非同步處理：將照片送至 Hume AI 進行表情分析，並執行卡控機制 (過濾前五名 > 40% 的結果)
    """
    async with httpx.AsyncClient(timeout=None) as client:
        # A. 建立 Hume AI 批次辨識任務工單
        headers = {"X-Hume-Api-Key": HUME_API_KEY}
        payload = {"models": {"face": {}}} # 啟用臉部表情分析模型
        
        # 以二進位讀取本地暫存圖片並封裝上傳
        with open(file_path, "rb") as f:
            upload_files = [("file", ("image.jpg", f, "image/jpeg"))]
            response = await client.post(
                BATCH_URL, 
                headers=headers, 
                data={"json": json.dumps(payload)}, 
                files=upload_files
            )
        
        # 驗證工單建立狀態，失敗時直接中斷
        if response.status_code not in [200, 201]:
            print(f"❌ Hume 任務建立失敗: {response.text}")
            return

        # 獲取 Hume 分發的任務識別碼 (Job ID)
        job_id = response.json().get("job_id")
        
        # B. 輪詢狀態 (Polling)：每隔 2 秒向伺服器確認是否分析完畢
        status_url = f"{BATCH_URL}/{job_id}"
        while True:
            res = await client.get(status_url, headers=headers)
            status = res.json().get("state", {}).get("status")
            if status == "COMPLETED": break # 分析成功，跳出迴圈
            if status in ["FAILED", "CANCELLED"]: return # 分析失敗或被取消，終止流程
            await asyncio.sleep(2) # 異步等待 2 秒後再次確認

        # C. 解析並過濾 Hume AI 回傳的數據
        pred_url = f"{BATCH_URL}/{job_id}/predictions"
        pred_res = await client.get(pred_url, headers={"X-Hume-Api-Key": HUME_API_KEY})
        if pred_res.status_code == 200:
            results = pred_res.json()
            # 深入 JSON 階層結構提取核心情緒陣列
            emotions = results[0]["results"]["predictions"][0]["models"]["face"]["grouped_predictions"][0]["predictions"][0]["emotions"]
            
            # 篩選步驟 1：依據分數 (Score) 由高到低重新排序，並切出前五名
            sorted_all = sorted(emotions, key=lambda x: x['score'], reverse=True)
            top_five = sorted_all[:5]
            
            # 篩選步驟 2：檢查這前五名中，是否有高於或等於 40% (0.4) 信心度的項目
            top_filtered = [e for e in top_five if e["score"] >= 0.4]

            if top_filtered:
                # 【情況 A】有高信心度情緒：代表辨識明確，直接將過濾後的結果自動存入資料庫
                filtered_data = {e["name"]: round(e["score"], 4) for e in top_filtered}
                save_to_postgres(test_id, filtered_data)
                return {"status": "success", "action": "auto_saved", "data": filtered_data}
            else:
                # 【情況 B】低信心度情緒 (全低於 40%)：回傳前五名，交由前端觸發自訂繁中彈窗供使用者手動校正
                options = {e["name"]: round(e["score"], 4) for e in top_five}
                return {"status": "low_confidence", "action": "user_selection_required", "options": options}


# --- 4. 路由 API 接口區 ---

@app.post("/api/save_manual")
async def save_manual(
    test_id: str = Form(...), 
    selected_emotion: str = Form(...), 
    score: float = Form(...)
):
    #接收使用者從 LIFF 前端自訂 Heal-Care 視窗中手動選取校正的情緒結果，並寫入資料庫
    try:
        # 將單一校正的情緒與分數封裝成標準字典，維持資料庫欄位 JSONB 格式的一致性
        manual_data = {selected_emotion: score}
        save_to_postgres(test_id, manual_data)
        return {"status": "success", "message": "手動選擇已存入資料庫"}
    except Exception as e:
        print(f"手動存檔路由發生錯誤: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/liff", response_class=HTMLResponse)
async def get_liff():
    #LINE 圖文選單導向專用路由：明確讀取並回傳精簡後的『照顧日誌明細與統計圖表頁面』
    try:
        with open("layout_test_Gen1.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "錯誤：找不到 layout_test_Gen1.html 檔案，請檢查整合目錄。"


@app.get("/", response_class=HTMLResponse)
async def get_index(liff_state: str = None):
    #系統主入口路由 (兼具 LINE LIFF 轉址阻斷判斷分流)
    # 當網址含有 liff.state 參數時，代表為 LINE 內部發出的特定頁面跳轉請求
    if liff_state:
        try:
            # 攔截此請求並自動分流返回精簡日誌圖表頁，避免其被預設的 index.html 阻斷
            with open("layout_test_Gen1.html", "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            pass
            
    # 正常網頁或外部電腦測試瀏覽時，預設回傳即時相機辨識與校正頁面
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()
    

@app.post("/api/upload")
async def handle_upload(file: UploadFile = File(...), test_id: str = Form(...)):
    #接收前端相機定時 4 秒傳送過來的圖片檔案，執行實體儲存並呼叫 Hume AI 核心線程
    file_path = IMAGE_DIR / file.filename
    try:
        # 將前端傳來的資料串流複製儲存到本地環境暫存夾
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # 關鍵架構優化：使用 await 直接掛起等待分析結果，完成後即時回傳給前端處理卡控
        result = await process_hume_ai(file_path, test_id)
        
        if result:
            return result
        else:
            return {"status": "error", "message": "分析失敗"}
            
    except Exception as e:
        print(f"圖片處理或 API 連線失敗: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/api/today_stats")
async def get_today_stats():
    #圖表對接專用 API：從 PostgreSQL 中過濾出今天的數據，進行次數累加統計並回傳
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        # 獲取今日日期，並利用 SQL CAST 比對 created_at 的日期部分
        today = date.today()
        query = "SELECT detected_emotions FROM emotion_logs WHERE CAST(created_at AS DATE) = %s"
        cur.execute(query, (today,))
        rows = cur.fetchall()
        
        # 遍歷今日的所有日誌紀錄，解開 JSONB 格式並將情緒名稱累加統計次數
        stats = {}
        for row in rows:
            emotions = row[0]  # row[0] 為一筆情緒 JSON 物件，例如 {"Calmness": 0.54}
            if emotions:
                for name in emotions.keys():
                    stats[name] = stats.get(name, 0) + 1
        
        cur.close()
        conn.close()
        # 回傳統計結果供前端 Chart.js 動態渲染圓餅圖
        return {"status": "success", "data": stats}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 專案主程式進入點：在本地 127.0.0.1:8000 埠號啟動 Uvicorn 異步伺服器
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)