@echo off
echo ========================================================
echo Starting AttendLens Full-Stack Production Server...
echo Department of Engineering & Technological Studies (DETS)
echo ========================================================
py main.py
if %ERRORLEVEL% NEQ 0 (
    python main.py
)
pause
