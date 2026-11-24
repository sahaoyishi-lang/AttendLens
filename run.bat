@echo off
cd /d "%~dp0"
echo ========================================================
echo Starting AttendLens Full-Stack Production Server...
echo Department of Engineering & Technological Studies (DETS)
echo ========================================================
echo Local Web Access: http://localhost:8000
echo Mobile Student Portal: http://localhost:8000/student
echo ========================================================
py main.py
if %ERRORLEVEL% NEQ 0 (
    python main.py
)
pause
