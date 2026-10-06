@echo off
set "CH=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%CH%" set "CH=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist "%CH%" set "CH=%LocalAppData%\Google\Chrome\Application\chrome.exe"
start "" "%CH%" --remote-debugging-port=9222 --user-data-dir="%LocalAppData%\hf_auto_chrome" --disable-background-timer-throttling --disable-renderer-backgrounding --disable-backgrounding-occluded-windows https://higgsfield.ai
