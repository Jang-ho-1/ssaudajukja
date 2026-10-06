@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PY=python
where py >nul 2>nul && set PY=py -3
%PY% -m pip install --upgrade playwright pillow
echo.
echo OK. Next: 2
pause
