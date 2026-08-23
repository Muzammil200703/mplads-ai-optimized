@echo off
title MPLADS AI Full-Stack Launcher
echo ========================================================
echo   MPLADS AI - Monitoring & Anomaly Detection System
echo ========================================================
echo.
echo [1/2] Starting FastAPI Backend on http://127.0.0.1:8000 ...
start "MPLADS Backend (FastAPI)" cmd /k "cd /d %~dp0backend && python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload"
echo.
echo [2/2] Starting React Frontend on http://localhost:5173 ...
start "MPLADS Frontend (Vite)" cmd /k "cd /d %~dp0frontend && npm run dev"
echo.
echo Both services launched!
echo - Frontend UI: http://localhost:5173
echo - Backend API: http://127.0.0.1:8000
echo - Swagger Docs: http://127.0.0.1:8000/docs
echo.
pause
