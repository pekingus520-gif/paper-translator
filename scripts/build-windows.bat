@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -m pip install -e ".[dev]"
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --name PaperTranslator --icon src\paper_translator\assets\paper-translator-icon.ico --paths src --collect-all uiautomation scripts\entrypoint.py
if errorlevel 1 goto failed
echo Built executable: dist\PaperTranslator\PaperTranslator.exe
echo Keep the entire dist\PaperTranslator folder together. Install Tesseract separately.
pause
exit /b 0
:failed
echo Build failed. Check the error above.
pause
exit /b 1
