@echo off
cd /d E:\GPT-SoVITS-v2pro-20250604
"E:\GPT-SoVITS-v2pro-20250604\runtime\python.exe" "E:\GPT-SoVITS-v2pro-20250604\api_v2.py" -a 0.0.0.0 -p 9880 -c "E:\GPT-SoVITS-v2pro-20250604\GPT_SoVITS\configs\maikeyase.yaml" 1>>"E:\GPT-SoVITS-v2pro-20250604\gpt-sovits-api.log" 2>>&1
