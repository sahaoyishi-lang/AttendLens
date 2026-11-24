@echo off
cd /d "%~dp0"
echo ========================================================
echo Starting AttendLens Public Cloudflare HTTPS Tunnel...
echo ========================================================
echo This generates a worldwide public HTTPS link for your app.
echo Keep this window open while you want public access.
echo ========================================================
cloudflared.exe tunnel --url http://localhost:8000
pause
