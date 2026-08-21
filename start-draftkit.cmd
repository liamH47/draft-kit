@echo off
REM Start draftkit and open it in a browser. Double-click this file.
REM
REM Your data - leagues, picks and tags - lives in backend\data and stays
REM there between runs. Closing this window stops the server; it does not
REM lose anything. Clearing your browser is harmless too: nothing is kept
REM in the browser at all.
setlocal
cd /d "%~dp0"

if exist "frontend\node_modules" goto build
echo Installing frontend packages, one time only...
cd frontend
call npm install --silent
cd ..

:build
echo Building the interface...
cd frontend
call npm run build
cd ..
set "DRAFTKIT_STATIC_DIR=..\frontend\dist"

if /i not "%~1"=="offline" goto run
echo.
echo DRAFT DAY MODE: refreshing every source now, then pinning to disk so
echo that a slow feed can never stall the board mid-draft.
cd backend
call uv run python scripts\warm_snapshots.py
cd ..
set "DRAFTKIT_OFFLINE=1"

:run
echo.
echo   draftkit is running at http://localhost:8000
echo   Leave this window open while you use it. Ctrl+C, or close it, to stop.
echo.
start "" http://localhost:8000
cd backend
uv run uvicorn draftkit.main:app --port 8000
