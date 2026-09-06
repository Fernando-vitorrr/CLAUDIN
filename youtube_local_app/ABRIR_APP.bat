@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
python app_youtube_local.py
if errorlevel 1 pause
