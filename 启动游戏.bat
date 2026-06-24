@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title Semantic Word Guess - Server

echo ============================================
echo   Semantic Word Guess - Launcher
echo ============================================
echo.
echo Starting backend... (first run loads model ~20s)
echo Open http://localhost:8000/ in your browser when ready.
echo Close this window to stop the server.
echo.

python server.py
if errorlevel 1 (
  echo.
  echo [ERROR] Start failed. Install dependencies first:
  echo   pip install sentence-transformers modelscope numpy
  echo.
  pause
)
