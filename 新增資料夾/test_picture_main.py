from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import json

app = FastAPI()

# 解決跨域問題 (CORS)，確保前端 fetch 正常
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

# 靜態檔案掛載，讓前端能透過 /images/0.png 讀取圖片
app.mount("/images", StaticFiles(directory=str(IMAGE_DIR)), name="images")

# 中英文情緒對照表
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

    # 遍歷圖片資料夾
    for img_path in IMAGE_DIR.iterdir():
        if img_path.suffix.lower() in valid_exts:
            # 尋找對應的結果檔 (例如: 0.png -> 0_result.json)
            result_file = RESULT_DIR / f"{img_path.stem}_result.json"
            translated_emotions = []
            
            if result_file.exists():
                try:
                    # 修正：使用 with 語句正確開啟檔案並定義 f
                    with open(result_file, "r", encoding="utf-8") as f:
                        raw_data = json.load(f)
                    
                    # 修正：針對 0_result.json 的 List 結構進行解析
                    if isinstance(raw_data, list) and len(raw_data) > 0:
                        main_data = raw_data[0]
                        predictions = main_data.get("results", {}).get("predictions", [])
            
                        if predictions and "models" in predictions[0]:
                            face_data = predictions[0]["models"]["face"]
                            grouped_preds = face_data.get("grouped_predictions", [])
                            
                            if grouped_preds:
                                # 取得情緒陣列
                                emotions = grouped_preds[0]["predictions"][0]["emotions"]
                                
                                # 排序並取前四名
                                top_emotions = sorted(emotions, key=lambda x: x["score"], reverse=True)[:4]
                                
                                # 修正：將翻譯後的資料存入 translated_emotions
                                for e in top_emotions:
                                    translated_emotions.append({
                                        "name": EMOTION_TRANSLATION.get(e["name"], e["name"]),
                                        "score": e["score"]
                                    })
                except Exception as e:
                    print(f"解析錯誤: {img_path.name} - {e}")

            # 只有當有成功解析出情緒時才加入列表，或保留空列表顯示「未偵測到情緒」
            logs.append({
                "image_url": f"/images/{img_path.name}",
                "emotions": translated_emotions
            })
            
    # 根據檔名排序，確保網頁顯示順序正確
    logs.sort(key=lambda x: x["image_url"])
    return logs

if __name__ == "__main__":
    import uvicorn
    # 啟動於 http://127.0.0.1:8000
    uvicorn.run(app, host="127.0.0.1", port=8000)