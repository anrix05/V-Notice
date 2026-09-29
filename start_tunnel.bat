@echo off
title V Notice - Cloudflare Remote Admin Tunnel
echo ==========================================================
echo        V NOTICE - SECURE REMOTE ADMIN TUNNEL
echo ==========================================================
echo Starting Cloudflare Tunnel for Admin Portal (Port 5001)...
echo.
"C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:5001
pause
