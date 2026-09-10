@echo off
setlocal
cd /d "%~dp0..\backend"
set PYTHON_EXE=E:\developtool\anaconda3\envs\sysmlv2\python.exe
"%PYTHON_EXE%" -m pip install -r requirements.txt
"%PYTHON_EXE%" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
