@echo off
setlocal
cd /d "%~dp0"
python -c "import flask, fitz, docx, PIL, bs4" >nul 2>&1
if errorlevel 1 (
  echo Installing required Python packages...
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo Installation failed. Check your internet connection and try again.
    pause
    exit /b 1
  )
)
echo Starting PDFeditorAthome. Your browser will open automatically.
echo Close the editor tab when finished to stop PDFeditorAthome.
python app.py
endlocal
