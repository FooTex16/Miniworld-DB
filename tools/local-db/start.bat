@echo off
cd /d "%~dp0"
title MiniWorld DB (localhost)
start "MiniWorld DB - server" cmd /k python -X utf8 server.py --port 8777
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8777/
