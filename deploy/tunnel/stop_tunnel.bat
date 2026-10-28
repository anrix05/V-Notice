@echo off
title Stop V Notice Tunnel
echo Stopping Cloudflare Tunnel...
taskkill /F /IM cloudflared.exe >nul 2>&1
echo Tunnel stopped successfully. Remote access is now closed.
pause
