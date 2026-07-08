@echo off
cd /d "%~dp0.."

set /p VERSION="Enter version (default 1.0.3): "
if "%VERSION%"=="" set VERSION=1.0.3
echo Building ImageHosting version %VERSION%
echo.

python -m PyInstaller --onedir --name ImageHosting --icon "assets\icon.ico" ^
  --add-data "templates;templates" --add-data "static;static" ^
  --add-data "assets\icon.ico;." --hidden-import PIL --hidden-import pystray ^
  --noconsole --clean app.py
if %ERRORLEVEL% neq 0 ( echo FAILED & pause & exit /b 1 )
echo OK - dist\ImageHosting (version %VERSION%)
pause
