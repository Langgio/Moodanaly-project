import os
import asyncio
import httpx
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, JSON, Date, Boolean, func
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, timedelta
from datetime import datetime, timezone
from typing import List

# --- 1. 資料庫配置 ---
SQLALCHEMY_DATABASE_URL = "postgresql://postgres:0@localhost:5432/postgres"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 需求 4：互動紀錄表
class Interaction(Base):
    __tablename__ = "interactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    family_id = Column(Integer, nullable=False)
    activity_name = Column(String)             # 新增：紀錄是哪部影片或活動
    face_emotions = Column(JSON)               # 原始數據
    top_4_candidates = Column(JSON)            # 新增：低信心值時的 4 個選項
    final_emotion = Column(String)             # 最終確定的情緒
    confidence = Column(Float)
    status = Column(String)                    # 'pending' 或 'confirmed'
    is_manual = Column(Boolean, default=False) # 是否為人工選擇
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class CareLog(Base):
    __tablename__ = "care_logs"
    id = Column(Integer, primary_key=True, index=True)
    family_id = Column(Integer, index=True)
    log_date = Column(Date, default=lambda: datetime.now(timezone.utc).date())
    emotion_score = Column(Integer)
    positive_count = Column(Integer, default=0) # 新增：正向情緒總數 (折線圖第一條線)
    negative_count = Column(Integer, default=0) # 新增：負向情緒總數 (折線圖第二條線)
    activity_summary = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

Base.metadata.create_all(bind=engine)

# --- 2. Hume AI 服務 ---
class HumeService:
    def __init__(self):
        # 記得在此輸入你的 API KEY
        self.api_key = "YOUR_HUME_API_KEY"
        self.url = "https://api.hume.ai/v1/models/predictions"
    # 這裡的 analyze_face 方法仍然是呼叫 Hume API 的地方，請根據 Hume 的 API 文件實作呼叫邏輯
    async def analyze_face(self, image_content: bytes):
        # 原有的 Hume AI 呼叫邏輯...
        pass
    # 這裡新增一個方法，專門用來從 Hume 的完整結果中提取前四名情緒
    def extract_top_4(self, full_results: list) -> list:
        """
        從真實的 Hume JSON 結構中提取前四名情緒
        """
        try:
            # 依照你提供的 JSON 路徑層層進入
            # predictions -> models -> face -> grouped_predictions -> predictions -> emotions
            predictions = full_results[0]["results"]["predictions"][0]
            face_data = predictions["models"]["face"]["grouped_predictions"][0]["predictions"][0]
            emotions = face_data["emotions"]
            
            # 排序並取前四名
            sorted_emotions = sorted(emotions, key=lambda x: x['score'], reverse=True)[:4]
            return sorted_emotions
        except (KeyError, IndexError, TypeError) as e:
            print(f"解析 Hume 資料出錯: {e}")
            return []

# --- 3. FastAPI 主程式 ---
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
# 重要：啟用 CORS，讓 LIFF 網頁可以存取這個 API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 生產環境建議指定具體網址
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

hume_service = HumeService()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- API 路由 ---
@app.get("/")
async def serve_spa():
    # 直接回傳你的入口 HTML 檔案
    return FileResponse("test.html")

# 供 LIFF 抓取最近 7 天情緒數據的路由
@app.get("/api/care-logs/{family_id}/summary")
async def get_care_summary(family_id: int, db: Session = Depends(get_db)):
    # 這裡實作從資料庫撈取最近 7 天數據的邏輯
    # 目前先回傳 Mock Data 供你 Week 2 測試介面用
    return {
        "labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "scores": [75, 62, 88, 45, 50, 92, 80],
        "summary": "本週長輩情緒穩定，週四午後稍微低落，建議多加關心。"
    }

@app.post("/analyze-emotion/{user_id}/{family_id}")
async def upload_and_analyze(
    user_id: int, 
    family_id: int, 
    activity_name: str, 
    file: UploadFile = File(...), 
    db: Session = Depends(get_db)
):
    # 1. 讀取並呼叫 Hume AI (這裡模擬獲取你提供的 JSON 內容)
    contents = await file.read()
    raw_results = await hume_service.analyze_face(contents) 
    
    # 2. 解析出前四名
    top_4 = hume_service.extract_top_4(raw_results)
    if not top_4:
        raise HTTPException(status_code=400, detail="無法從圖片中辨識臉部情緒")

    # 3. 信心值邏輯判斷
    top_1 = top_4[0]
    threshold = 0.7  # 你的需求：低於 70% 標記不確定
    
    is_high_confidence = top_1['score'] >= threshold
    status = "confirmed" if is_high_confidence else "pending"

    # 4. 寫入資料庫
    new_interaction = Interaction(
        user_id=user_id,
        family_id=family_id,
        activity_name=activity_name,
        face_emotions=raw_results,      # 存入完整原始 JSON
        top_4_candidates=top_4,        # 存入排序後的前四名 (方便前端直接用)
        final_emotion=top_1['name'] if is_high_confidence else None,
        confidence=top_1['score'],
        status=status
    )
    db.add(new_interaction)
    db.commit()
    db.refresh(new_interaction)

    # 5. 回傳給前端
    return {
        "id": new_interaction.id,
        "status": status,
        "action": "none" if is_high_confidence else "require_manual_selection",
        "candidates": top_4  # 這樣前端就不需要自己解析 JSON 了，直接拿這四筆資料顯示
    }

# 步驟 3 & 4：人工從四種情緒選一種記入
@app.post("/confirm-emotion/{interaction_id}")
async def confirm_emotion(interaction_id: int, selected_emotion: str, db: Session = Depends(get_db)):
    record = db.query(Interaction).filter(Interaction.id == interaction_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    
    record.final_emotion = selected_emotion
    record.status = "confirmed"
    record.is_manual = True
    db.commit()
    return {"status": "success", "confirmed_emotion": selected_emotion}

# 步驟 5：每日結算生成日誌
@app.post("/api/generate-daily-log/{family_id}")
async def generate_daily_log(family_id: int, selected_ids: List[int], db: Session = Depends(get_db)):
    # 1. 抓取被勾選的這些互動紀錄
    records = db.query(Interaction).filter(Interaction.id.in_(selected_ids)).all()
    emotions_summary = [r.final_emotion for r in records if r.final_emotion]
    
    # 2. 這裡應呼叫 LLM (例如 GPT/Gemini) 傳入 emotions_summary 生成文字
    ai_summary = f"今日長輩情緒包含 {', '.join(set(emotions_summary))}。整體表現穩定..."
    
    # 3. 寫入 CareLog
    new_log = CareLog(
        family_id=family_id,
        emotion_score=75, # 這裡可根據情緒權重計算分數
        activity_summary=ai_summary
    )
    db.add(new_log)
    db.commit()
    return {"status": "log_created", "summary": ai_summary}

# [今天分頁] 取得圓餅圖與下方表格
@app.get("/api/dashboard/today/{family_id}")
async def get_today_data(family_id: int, db: Session = Depends(get_db)):
    today = datetime.now(timezone.utc).date()
    # 抓取今天已確認的所有情緒
    records = db.query(Interaction).filter(
        Interaction.family_id == family_id,
        func.date(Interaction.created_at) == today,
        Interaction.status == "confirmed"
    ).all()

    # 計算圓餅圖佔比
    pie_data = {}
    for r in records:
        pie_data[r.final_emotion] = pie_data.get(r.final_emotion, 0) + 1

    return {
        "pie_chart": pie_data,
        "table": [
            {"time": r.created_at.strftime("%H:%M"), "activity": r.activity_name, "emotion": r.final_emotion}
            for r in records
        ]
    }

# [歷史分頁] 取得雙線折線圖數據
@app.get("/api/dashboard/history/{family_id}")
async def get_history_data(family_id: int, db: Session = Depends(get_db)):
    # 抓取最近 30 天的 CareLog
    logs = db.query(CareLog).filter(CareLog.family_id == family_id).order_by(CareLog.log_date.desc()).limit(30).all()
    logs.reverse() # 轉為由舊到新
    
    return {
        "labels": [log.log_date.strftime("%m/%d") for log in logs],
        "positive_line": [log.positive_count for log in logs],
        "negative_line": [log.negative_count for log in logs],
        "dates": [log.log_date.isoformat() for log in logs]
    }

# [歷史分頁] 點擊折線圖某點後，取得當天明細表格
@app.get("/api/dashboard/history-detail/{family_id}/{target_date}")
async def get_history_detail(family_id: int, target_date: str, db: Session = Depends(get_db)):
    records = db.query(Interaction).filter(
        Interaction.family_id == family_id,
        func.date(Interaction.created_at) == target_date,
        Interaction.status == "confirmed"
    ).all()
    
    return [
        {"time": r.created_at.strftime("%H:%M"), "activity": r.activity_name, "emotion": r.final_emotion}
        for r in records
    ]

if __name__ == "__main__":
    import uvicorn
    # host="0.0.0.0" 讓同網路的其他裝置也能存取，port 8000 是預設埠號
    uvicorn.run(app, host="0.0.0.0", port=8000)