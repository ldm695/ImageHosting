@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0.."

echo [1/4] PyInstaller - bundling app...
python -m PyInstaller --onedir --name ImageHosting --icon "assets\icon.ico" --add-data "templates;templates" --add-data "static;static" --add-data "assets\icon.ico;." --hidden-import PIL --hidden-import pystray --noconsole --clean app.py
if %ERRORLEVEL% neq 0 ( echo FAILED & pause & exit /b 1 )
echo OK

echo [2/4] heat.exe - harvesting file list...
copy /Y "assets\icon.ico" "dist\ImageHosting\icon.ico" >nul
heat.exe dir "dist\ImageHosting" -nologo -ag -cg HarvestedFiles -dr INSTALLDIR -srd -var "var.SourceDir" -out "dist\ImageHosting.wxs"
if %ERRORLEVEL% neq 0 ( echo heat.exe FAILED & pause & exit /b 1 )
echo OK

echo [3/4] candle.exe - compiling...
candle.exe "scripts\installer.wxs" "dist\ImageHosting.wxs" -nologo -dSourceDir="dist\ImageHosting" -out "dist\\"
if %ERRORLEVEL% neq 0 ( echo FAILED & pause & exit /b 1 )
echo OK

echo [4/4] light.exe - linking MSI...
light.exe "dist\installer.wixobj" "dist\ImageHosting.wixobj" -nologo -ext WixUIExtension -cultures:en-US -out "dist\ImageHosting-1.0.1.msi"
if %ERRORLEVEL% neq 0 ( echo FAILED & pause & exit /b 1 )

echo SUCCESS - dist\ImageHosting-1.0.1.msi
pause
endlocal
