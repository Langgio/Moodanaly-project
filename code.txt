import os
import httpx
import json
import asyncio
from pathlib import Path

# --- 設定區 ---
HUME_API_KEY = "YRolQS4LUtijkq8V89lMsneS1PGgRZYdXlf3T64ELG73z1fa" 
VIDEO_PATH = Path("799140235.700015.mp4")
RESULT_DIR = "testhumiai/result"
# 建議使用 v1 版本 API
BATCH_URL = "https://api.hume.ai/v1/batch/jobs" 

async def start_video_job(client, video_p):
    headers = {"X-Hume-Api-Key": HUME_API_KEY}
    
    # 修正點 1：明確指定影片的 MIME Type
    mime_type = "video/mp4"
    
    # 修正點 2：使用英文虛擬檔名 "input_video.mp4" 徹底避開中文路徑/編碼地雷
    # 這裡用 open 搭配 with 確保檔案會被正確關閉
    with open(video_p, "rb") as f:
        upload_files = [
            ("file", ("input_video.mp4", f, mime_type))
        ]

        # 修正點 3：Hume API 預期 'json' 欄位包含模型配置
        payload = {"models": {"face": {}}}
        form_data = {"json": json.dumps(payload)}
        
        try:
            print(f"🚀 正在上傳影片: {video_p.name}...")
            # timeout 設為 None 避免大影片上傳到一半斷掉
            response = await client.post(
                BATCH_URL, 
                headers=headers, 
                data=form_data, 
                files=upload_files, 
                timeout=None 
            )
            
            if response.status_code in [200, 201]:
                job_id = response.json().get("job_id")
                print(f"✅ 任務建立成功！Job ID: {job_id}")
                return job_id
            else:
                print(f"❌ 建立失敗，代碼: {response.status_code}")
                print(f"錯誤內容: {response.text}")
                return None
        except Exception as e:
            print(f"❌ 上傳發生異常: {e}")
            return None

async def wait_for_job(client, job_id):
    headers = {"X-Hume-Api-Key": HUME_API_KEY}
    status_url = f"{BATCH_URL}/{job_id}"
    print("⏳ Hume AI 正在分析影片情緒，這可能需要一點時間...")
    
    while True:
        try:
            response = await client.get(status_url, headers=headers)
            job_data = response.json()
            status = job_data.get("state", {}).get("status")
            print(f"   目前狀態: {status}")
            
            if status == "COMPLETED": 
                return True
            if status in ["FAILED", "CANCELLED"]: 
                print(f"❌ 任務失敗，原因: {job_data.get('state', {}).get('message')}")
                return False
        except Exception as e:
            print(f"⚠️ 輪詢發生錯誤 (稍後重試): {e}")
            
        await asyncio.sleep(10) # 影片處理較久，建議間隔拉長

async def download_results(client, job_id):
    headers = {"X-Hume-Api-Key": HUME_API_KEY}
    predictions_url = f"{BATCH_URL}/{job_id}/predictions"
    
    print("📥 正在下載辨識結果...")
    response = await client.get(predictions_url, headers=headers)
    
    if response.status_code == 200:
        results = response.json()
        Path(RESULT_DIR).mkdir(parents=True, exist_ok=True)
        
        # 儲存完整的 JSON
        output_path = Path(RESULT_DIR) / "video_emotion_result.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=4, ensure_ascii=False)
        print(f"🎉 處理完成！結果已存至 {output_path}")

async def main():
    if not VIDEO_PATH.exists():
        print(f"Error: 找不到檔案 {VIDEO_PATH}")
        return

    # 建議在 AsyncClient 初始化時設定不限時，應對大型上傳
    async with httpx.AsyncClient(timeout=None) as client:
        job_id = await start_video_job(client, VIDEO_PATH)
        if job_id and await wait_for_job(client, job_id):
            await download_results(client, job_id)

if __name__ == "__main__":
    asyncio.run(main())