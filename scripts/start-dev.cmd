@echo off
setlocal

set "ROOT=%~dp0.."
set "FRONTEND_DIR=%ROOT%\frontend"
set "BACKEND_PORT=8000"
set "FRONTEND_PORT=3000"

if not exist "%FRONTEND_DIR%\node_modules" (
  echo frontend\node_modules not found. Running npm install first...
  pushd "%FRONTEND_DIR%"
  call npm install
  if errorlevel 1 (
    popd
    echo npm install failed.
    exit /b 1
  )
  popd
)

echo Starting backend on http://127.0.0.1:%BACKEND_PORT%
start "Voice TA Backend" cmd /k "cd /d ""%ROOT%"" && conda run -n voiceTA python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port %BACKEND_PORT%"

echo Starting frontend on http://localhost:%FRONTEND_PORT%
start "Voice TA Frontend" cmd /k "cd /d ""%FRONTEND_DIR%"" && set NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:%BACKEND_PORT%&& npm run dev -- --port %FRONTEND_PORT%"

echo.
echo Voice TA development services are starting.
echo Backend:  http://127.0.0.1:%BACKEND_PORT%
echo Frontend: http://localhost:%FRONTEND_PORT%
echo.
echo Close the two opened terminal windows to stop the services.

endlocal
