@echo off
setlocal

:: V Notice Kiosk Launcher for Windows
:: Launches Chrome or Edge with autoplay unlocked and dedicated kiosk profile

set "DISPLAY_URL=%~1"
if "%DISPLAY_URL%"=="" (
  set "DISPLAY_URL=https://v-notice.onrender.com/display/ALL"
)

set "KIOSK_DATA_DIR=%LOCALAPPDATA%\VNoticeKiosk"
if not exist "%KIOSK_DATA_DIR%" mkdir "%KIOSK_DATA_DIR%"

:: Locate Google Chrome or Microsoft Edge
set "BROWSER_BIN="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
  set "BROWSER_BIN=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
) else if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (
  set "BROWSER_BIN=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
) else if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" (
  set "BROWSER_BIN=%LocalAppData%\Google\Chrome\Application\chrome.exe"
) else if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" (
  set "BROWSER_BIN=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
) else if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" (
  set "BROWSER_BIN=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
)

if "%BROWSER_BIN%"=="" (
  echo [ERROR] Neither Google Chrome nor Microsoft Edge was found.
  echo Please install Chrome or Edge to launch the V Notice display kiosk.
  pause
  exit /b 1
)

echo Starting V Notice kiosk for %DISPLAY_URL%...
start "" "%BROWSER_BIN%" --kiosk "%DISPLAY_URL%" --autoplay-policy=no-user-gesture-required --user-data-dir="%KIOSK_DATA_DIR%" --noerrdialogs --disable-infobars --start-fullscreen
