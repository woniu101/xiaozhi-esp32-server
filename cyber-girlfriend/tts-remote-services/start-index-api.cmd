@echo off
cd /d E:\IndexTTS-2.5
"E:\IndexTTS-2.5\python_embeded\python.exe" -u -m uvicorn index_api.app:app --app-dir "E:\IndexTTS-2.5" --host 192.168.18.14 --port 8092 --workers 1 1>>"E:\IndexTTS-2.5\index-api.log" 2>>&1
