@echo off
setlocal
cd /d "%~dp0..\frontend"
set "BUNDLED_NODE=C:\Users\13101\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin"
set "BUNDLED_PNPM=C:\Users\13101\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\pnpm.cmd"
set "NODE_EXE=%BUNDLED_NODE%\node.exe"
set "PATH=%BUNDLED_NODE%;%PATH%"

if not exist "%NODE_EXE%" (
  set "NODE_EXE=node"
)

if not exist node_modules (
  where npm >nul 2>nul
  if not errorlevel 1 (
    npm install
  ) else (
    if exist "%BUNDLED_PNPM%" (
      "%BUNDLED_PNPM%" install
    ) else (
      echo node_modules not found, and neither npm nor pnpm is available.
      echo Please install dependencies first, or install Node.js/npm.
      pause
      exit /b 1
    )
  )
)

where npm >nul 2>nul
if not errorlevel 1 (
  npm run dev
) else (
  if exist "node_modules\vite\bin\vite.js" (
    "%NODE_EXE%" "node_modules\vite\bin\vite.js" --host 0.0.0.0
  ) else (
    echo Unable to start frontend: npm was not found and local Vite is missing.
    pause
    exit /b 1
  )
)
