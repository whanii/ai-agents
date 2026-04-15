@echo off
setlocal

cd /d "%~dp0"
if not exist logs mkdir logs

set "LOG_MONTH=%date:~0,4%-%date:~5,2%"
set "LOG_FILE=logs\run_daily_report_%LOG_MONTH%.log"

echo.>> "%LOG_FILE%"
echo [%date% %time%] Starting daily report pipeline... >> "%LOG_FILE%"
python scripts\run_pipeline.py >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail

python scripts\build_pages.py >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail

git add reports ..\docs >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail

git diff --cached --quiet
if errorlevel 1 (
    git commit -m "Update daily AI trend report" >> "%LOG_FILE%" 2>&1
    if errorlevel 1 goto :fail

    git push origin main >> "%LOG_FILE%" 2>&1
    if errorlevel 1 goto :fail

    echo [%date% %time%] Git push completed. >> "%LOG_FILE%"
) else (
    echo [%date% %time%] No report changes to commit. >> "%LOG_FILE%"
)

echo [%date% %time%] Finished with exit code 0. >> "%LOG_FILE%"

endlocal
exit /b 0

:fail
set "EXIT_CODE=%ERRORLEVEL%"
echo [%date% %time%] Finished with exit code %EXIT_CODE%. >> "%LOG_FILE%"
endlocal
exit /b %EXIT_CODE%
