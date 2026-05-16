import os
import httpx
import json
import asyncio
from pathlib import Path

# --- 設定區 ---
HUME_API_KEY = "YRolQS4LUtijkq8V89lMsneS1PGgRZYdXlf3T64ELG73z1fa"
# 設定圖片來源資料夾
IMAGE_FOLDER_PATH = Path(r"D:\工作\CODE\python\Moodanaly-project\testhumiai")
# 設定結果儲存資料夾
RESULT_DIR = IMAGE_FOLDER_PATH / "result"
# 使用 v0 或 v1 版本 API
BATCH_URL = "https://api.hume.ai/v0/batch/jobs"
# 限制併發上傳數量，避免 SSL 錯誤或網路塞車
MAX_CONCURRENT_REQUESTS = 5

async def process_image_to_file(semaphore, client, img_p):
    """處理單張圖片並儲存為獨立檔案"""
    async with semaphore:
        headers = {"X-Hume-Api-Key": HUME_API_KEY}
        ext = img_p.suffix.lower()
        mtype = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"

        # --- 修正點：配合後端邏輯，將結果檔名改為 圖片主檔名_result.json ---
        # 例如: 0.png -> 0_result.json 
        output_filename = RESULT_DIR / f"{img_p.stem}_result.json"
        
        # 如果結果已存在，跳過 (可作為續傳功能)
        if output_filename.exists():
            print(f"⏭️  {img_p.name} 的結果已存在，跳過。")
            return

        try:
            # 1. 上傳單張圖片
            with open(img_p, "rb") as f:
                files = [("file", (img_p.name, f, mtype))]
                payload = {"models": {"face": {}}}
                form_data = {"json": json.dumps(payload)}
                
                print(f"🚀 正在上傳: {img_p.name}")
                response = await client.post(
                    BATCH_URL, headers=headers, data=form_data, files=files
                )
            
            if response.status_code not in [200, 201]:
                print(f"❌ {img_p.name} 上傳失敗: {response.status_code}")
                return

            job_id = response.json().get("job_id")
            
            # 2. 輪詢狀態
            status_url = f"{BATCH_URL}/{job_id}"
            while True:
                await asyncio.sleep(5)
                res = await client.get(status_url, headers=headers)
                status = res.json().get("state", {}).get("status")
                
                if status == "COMPLETED":
                    break
                if status in ["FAILED", "CANCELLED"]:
                    print(f"❌ {img_p.name} 任務失敗")
                    return

            # 3. 下載結果並儲存為單一 JSON
            pred_url = f"{BATCH_URL}/{job_id}/predictions"
            dl_res = await client.get(pred_url, headers=headers)
            if dl_res.status_code == 200:
                with open(output_filename, "w", encoding="utf-8") as f_out:
                    json.dump(dl_res.json(), f_out, indent=4, ensure_ascii=False)
                print(f"✅ {img_p.name} 處理完成 -> {output_filename.name}")
        except Exception as e:
            print(f"⚠️ {img_p.name} 發生異常: {e}")

async def run_individual_batch():
    if not IMAGE_FOLDER_PATH.exists():
        print(f"❌ 找不到路徑: {IMAGE_FOLDER_PATH}")
        return

    # 確保結果目錄存在
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    # 搜尋所有圖片格式
    image_files = list(IMAGE_FOLDER_PATH.glob("*.jpg")) + \
                  list(IMAGE_FOLDER_PATH.glob("*.jpeg")) + \
                  list(IMAGE_FOLDER_PATH.glob("*.png"))

    if not image_files:
        print("ℹ️ 無圖片檔案")
        return

    print(f"📦 準備處理 {len(image_files)} 張圖片，結果將分開儲存...")

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    async with httpx.AsyncClient(timeout=None) as client:
        # 同時建立任務
        tasks = [process_image_to_file(semaphore, client, img_p) for img_p in image_files]
        await asyncio.gather(*tasks)

    print(f"\n🎉 批次處理結束！請至 {RESULT_DIR} 查看結果。")

if __name__ == "__main__":
    asyncio.run(run_individual_batch())