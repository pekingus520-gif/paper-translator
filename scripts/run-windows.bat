@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 goto failed
  .venv\Scripts\python.exe -m pip install -e .
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -m paper_translator %*
if errorlevel 1 goto failed
exit /b 0
:failed
echo Startup failed. Install Python 3.10+ and check the error above.
pause
exit /b 1
