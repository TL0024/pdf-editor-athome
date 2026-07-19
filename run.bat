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
echo PDFeditorAthome is running at http://127.0.0.1:5050
echo Close the editor tab when finished to stop PDFeditorAthome.
start "" http://127.0.0.1:5050
python app.py
endlocal
