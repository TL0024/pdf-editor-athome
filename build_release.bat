@echo off
setlocal
cd /d "%~dp0"

set /p VERSION=<VERSION
if not defined VERSION goto :missing_version
set "BUILD_PY=.build-venv\Scripts\python.exe"
set "RELEASE_DIR=release\PDFeditorAthome-v%VERSION%-windows-x64"
set "RELEASE_ZIP=release\PDFeditorAthome-v%VERSION%-windows-x64.zip"

if not exist "%BUILD_PY%" (
  echo Creating isolated build environment...
  python -m venv .build-venv
  if errorlevel 1 goto :error
)

echo Synchronizing pinned release dependencies...
"%BUILD_PY%" -m pip install --disable-pip-version-check -r requirements-release.txt
if errorlevel 1 goto :error

echo Building PDFeditorAthome.exe...
"%BUILD_PY%" -m PyInstaller --noconfirm --clean PDFeditorAthome.spec
if errorlevel 1 goto :error
if not exist "dist\PDFeditorAthome.exe" goto :missing

if not exist "release" mkdir "release"
if not exist "%RELEASE_DIR%" mkdir "%RELEASE_DIR%"
copy /y "dist\PDFeditorAthome.exe" "%RELEASE_DIR%\PDFeditorAthome.exe" >nul
copy /y "packaging\RELEASE_README.txt" "%RELEASE_DIR%\README.txt" >nul
copy /y "docs\THIRD_PARTY.md" "%RELEASE_DIR%\THIRD_PARTY.md" >nul

powershell -NoProfile -Command "$h = (Get-FileHash -Algorithm SHA256 -LiteralPath '%RELEASE_DIR%\PDFeditorAthome.exe').Hash.ToLowerInvariant(); Set-Content -LiteralPath '%RELEASE_DIR%\SHA256SUMS.txt' -Value ($h + '  PDFeditorAthome.exe') -Encoding ascii"
if errorlevel 1 goto :error

echo Creating release archive...
powershell -NoProfile -Command "Compress-Archive -Path '%RELEASE_DIR%\PDFeditorAthome.exe','%RELEASE_DIR%\README.txt','%RELEASE_DIR%\THIRD_PARTY.md','%RELEASE_DIR%\SHA256SUMS.txt' -DestinationPath '%RELEASE_ZIP%' -Force"
if errorlevel 1 goto :error

echo.
echo Release created successfully:
echo   %RELEASE_ZIP%
exit /b 0

:missing
echo Build finished without creating dist\PDFeditorAthome.exe.
exit /b 1

:missing_version
echo VERSION is empty or missing.
exit /b 1

:error
echo PDFeditorAthome release build failed.
exit /b 1
