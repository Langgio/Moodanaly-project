from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import json

app = FastAPI()

# 新增 CORS 設定以解決 Failed to fetch 問題
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 設定路徑
BASE_PATH = Path(r"D:\工作\CODE\python\Moodanaly-project")
IMAGE_DIR = BASE_PATH / "testhumiai"
RESULT_DIR = IMAGE_DIR / "result"

# 靜態檔案掛載
app.mount("/images", StaticFiles(directory=str(IMAGE_DIR)), name="images")

# 建立中英文情緒對照表 (對應 Hume AI 48 種情緒)
EMOTION_TRANSLATION = {
    "Admiration": "讚賞", "Adoration": "崇拜", "Aesthetic Appreciation": "審美感知",
    "Amusement": "幽默", "Anger": "憤怒", "Anxiety": "焦慮", "Awe": "敬畏",
    "Awkwardness": "尷尬", "Boredom": "乏味", "Calmness": "冷靜",
    "Concentration": "專注", "Confusion": "困惑", "Contemplation": "沉思",
    "Contempt": "輕蔑", "Contentment": "滿足", "Craving": "渴望",
    "Desire": "慾望", "Determination": "堅定", "Disappointment": "失望",
    "Disgust": "厭惡", "Distress": "痛苦", "Doubt": "懷疑", "Ecstasy": "狂喜",
    "Embarrassment": "難堪", "Empathic Pain": "感同身受", "Entrancement": "著迷",
    "Envy": "嫉妒", "Excitement": "興奮", "Fear": "恐懼", "Guilt": "內疚",
    "Horror": "恐怖", "Interest": "興趣", "Joy": "喜悅", "Love": "愛",
    "Nostalgia": "懷舊", "Pain": "痛楚", "Pride": "自豪", "Realization": "體悟",
    "Relief": "解脫", "Romance": "浪漫", "Sadness": "悲傷", "Satisfaction": "滿意",
    "Shame": "羞恥", "Surprise (negative)": "驚訝(負面)", "Surprise (positive)": "驚訝(正面)",
    "Sympathy": "同情", "Tiredness": "疲勞", "Triumph": "勝利"
}

@app.get("/api/logs")
async def get_logs():
    logs = []
    valid_exts = [".jpg", ".jpeg", ".png"]
    
    if not IMAGE_DIR.exists():
        return {"error": "找不到指定路徑"}

    for img_path in IMAGE_DIR.iterdir():
        if img_path.suffix.lower() in valid_exts:
            # 尋找對應的結果檔 
            result_file = RESULT_DIR / f"{img_path.stem}_result.json"
            translated_emotions = []
            
            if result_file.exists():
                with open(result_file, "r", encoding="utf-8") as f:
                    try:
                        raw_data = json.load(f)
                        # 提取情緒清單 
                        emotions = raw_data["results"]["predictions"][0]["models"]["face"]["grouped_predictions"][0]["predictions"][0]["emotions"]
                        
                        # 排序並取前四名，同時進行中文翻譯
                        top_emotions = sorted(emotions, key=lambda x: x["score"], reverse=True)[:4]
                        for e in top_emotions:
                            translated_emotions.append({
                                "name": EMOTION_TRANSLATION.get(e["name"], e["name"]), # 查不到則顯示原文
                                "score": e["score"]
                            })
                    except Exception as e:
                        print(f"解析錯誤: {img_path.name} - {e}")

            logs.append({
                "image_url": f"/images/{img_path.name}",
                "emotions": translated_emotions
            })
    return logs

if __name__ == "__main__":
    import uvicorn
    # 固定 port 8000
    uvicorn.run(app, host="127.0.0.1", port=8000)