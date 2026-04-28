@echo off
setlocal

cd /d "%~dp0"
if not exist logs mkdir logs

set "LOG_MONTH=%date:~0,4%-%date:~5,2%"
set "LOG_FILE=logs\run_daily_report_%LOG_MONTH%.log"

echo.>> "%LOG_FILE%"
echo Starting daily report pipeline...
echo [%date% %time%] Starting daily report pipeline... >> "%LOG_FILE%"
echo Running pipeline...
python scripts\run_pipeline.py >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail

echo Building docs site...
python scripts\build_pages.py >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail

echo Staging reports and docs...
git add reports ..\docs >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail

git diff --cached --quiet
if errorlevel 1 (
    echo Committing changes...
    git commit -m "Update daily AI trend report" >> "%LOG_FILE%" 2>&1
    if errorlevel 1 goto :fail

    echo Pushing to origin/main...
    git push origin main >> "%LOG_FILE%" 2>&1
    if errorlevel 1 goto :fail

    echo Git push completed.
    echo [%date% %time%] Git push completed. >> "%LOG_FILE%"
) else (
    echo No report changes to commit.
    echo [%date% %time%] No report changes to commit. >> "%LOG_FILE%"
)

echo Finished successfully.
echo [%date% %time%] Finished with exit code 0. >> "%LOG_FILE%"

endlocal
exit /b 0

:fail
set "EXIT_CODE=%ERRORLEVEL%"
echo Failed with exit code %EXIT_CODE%. Check %LOG_FILE%.
echo [%date% %time%] Finished with exit code %EXIT_CODE%. >> "%LOG_FILE%"
endlocal
exit /b %EXIT_CODE%
