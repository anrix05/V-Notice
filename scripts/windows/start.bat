@echo off
title V Notice - Smart Digital Notice Board
cd /d "%~dp0..\.."
echo Starting V Notice Dual Server (Display: Port 5000, Admin: Port 5001)...
python app.py
pause
