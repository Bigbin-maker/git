@echo off
set MAGICDRAW_EXE=E:\software\Catiamagic2022\bin\magicdraw.exe

if not exist "%MAGICDRAW_EXE%" (
  echo MagicDraw executable not found: %MAGICDRAW_EXE%
  exit /b 1
)

start "MagicDraw Bridge" "%MAGICDRAW_EXE%"
echo MagicDraw is starting. The AI-MBSE Bridge listens on http://127.0.0.1:7010/api after MagicDraw finishes loading.
