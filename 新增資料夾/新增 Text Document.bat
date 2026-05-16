@echo off
chcp 65001 > nul
D:
cd /d "D:\工作\CODE\python\Moodanaly-project"
:: 啟動虛擬環境並執行 uvicorn
call venv\Scripts\activate
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
pause