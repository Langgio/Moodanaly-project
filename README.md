**你只會需要readytopush的檔案**

**Moodanaly-project 情感辨識與照顧日誌**

*1\. 檔案清單與專案架構*

*\`init_db.sql\`：本地 PostgreSQL 資料庫的環境初始化腳本。*

*\`requirements.txt\`：Python 執行環境依賴套件清單。*

*\`server.py\`：後端主程式 (FastAPI)，內含 Hume AI 輪詢、資料庫寫入、網域動態分流路由。*

*\`index.html\`：前端鏡頭 4 秒定時自動拍上傳，與 Heal-Care 風格自訂繁中手動校正彈窗頁面。*

*\`layout_test_Gen1.html\`：LINE 官方帳號圖文選單點選後，專屬開啟的「照顧日誌明細與動態圖表」頁面。*

*\---*

**2\. 環境配置與資料庫設定**

*A. Hume AI 憑證位置*

*開啟 \`server.py\`，請在第 16 行左右找到 \`HUME_API_KEY\` 變數，並將其替換為您團隊專屬的 Hume AI Batch API 金鑰。*

*B. PostgreSQL 資料庫建立*

*請在本地 PostgreSQL 資料庫中執行 \`init_db.sql\`，或手動執行以下語法建立資料表。請注意，為了支援彈性的多模態分析，情緒數據是以 \`JSONB\` 格式規格化封裝：*

*sql*

*CREATE TABLE emotion_logs (*

*id SERIAL PRIMARY KEY,*

*test_name VARCHAR(255),*

*detected_emotions JSONB, -- 以 JSON 鍵值對儲存，如 {"Calmness": 0.85, "Joy": 0.42}*

*created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP*

*);*

*連線參數（如 DB Name、Password 等）請至 server.py 的 DB_CONFIG 字典中進行微調。*

**3\. 本地啟動與環境部署**

*安裝 Python 套件依賴項：*

*Bash*

*pip install -r requirements.txt*

*啟動後端異步伺服器：*

*Bash*

*python server.py*

*服務將預設啟動於 <http://127.0.0.1:8000。>*

*LINE LIFF / ngrok 部署注意點：*

*當使用 ngrok 對外映射服務時，請務必將 LINE Developers 平台的 LIFF Endpoint URL 設定導向後端的 /liff 路由（例如：https://&lt;您的-ngrok-隨機網域&gt;.ngrok-free.app/liff）。*

*後端根目錄 / 設有 liff_state 參數攔截與自動分流機制，能有效防止 LINE 轉址時造成的路由阻斷，確保手機端直接切入日誌明細頁，而電腦測試端保持載入相機辨識頁 (index.html)。*

**4\. 後端 API 規格說明書**

*① 圖片分析上傳接口*

*路由：POST /api/upload*

*參數：file (二進位圖片檔案), test_id (字串，如 'test 1')*

*商務邏輯：系統會將圖片拋送至 Hume AI 進行 2 秒一次的狀態輪詢 (Polling)。*

*情況 A (信心度 ≥ 40%)：過濾出前五名並直接自動寫入 PostgreSQL，回傳 {"status": "success", "action": "auto_saved"}。*

*情況 B (全低於 40%)：判定為低信心度，回傳前五名候選清單 {"status": "low_confidence", "action": "user_selection_required", "options": {...}}，交由前端觸發自訂繁中彈窗。*

*② 手動校正寫入接口*

*路由：POST /api/save_manual*

*參數：test_id (Form 欄位), selected_emotion (英文情緒代碼), score (數值)*

*說明：用於接收使用者從前端彈窗點選的單一確切情緒，並將其格式化為標準 JSONB 倒回資料庫。*

*③ 今日統計圖表接口*

*路由：GET /api/today_stats*

*回傳範例：{"status": "success", "data": {"Calmness": 3, "Joy": 1}}*

*說明：layout_test_Gen1.html 中的 Chart.js 圓餅圖會在頁面載入時自動 fetch 此接口，即時計算並累加今日在資料庫中的所有真實紀錄。*
