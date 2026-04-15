@echo off
setlocal

cd /d "%~dp0"
if not exist logs mkdir logs

set "LOG_MONTH=%date:~0,4%-%date:~5,2%"
set "LOG_FILE=logs\run_daily_report_%LOG_MONTH%.log"

echo.>> "%LOG_FILE%"
echo [%date% %time%] Starting daily report pipeline... >> "%LOG_FILE%"
python scripts\run_pipeline.py >> "%LOG_FILE%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
echo [%date% %time%] Finished with exit code %EXIT_CODE%. >> "%LOG_FILE%"

endlocal
exit /b %EXIT_CODE%
