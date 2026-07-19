@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0.."

set /p VERSION="Enter version (default 1.0.0): "
if "%VERSION%"=="" set VERSION=1.0.0
echo Building ImageHosting version %VERSION%
echo.

echo [1/5] PyInstaller - bundling app...
python -m PyInstaller --onedir --name ImageHosting --contents-directory "." --icon "assets\icon.ico" --add-data "templates;templates" --add-data "static;static" --add-data "assets\icon.ico;." --hidden-import PIL --hidden-import pystray --noconsole --clean app.py
if %ERRORLEVEL% neq 0 ( echo FAILED & pause & exit /b 1 )
echo OK

echo [2/5] heat.exe - harvesting file list...
copy /Y "assets\icon.ico" "dist\ImageHosting\icon.ico" >nul
heat.exe dir "dist\ImageHosting" -nologo -ag -cg HarvestedFiles -dr INSTALLDIR -srd -var "var.SourceDir" -out "dist\ImageHosting.wxs"
if %ERRORLEVEL% neq 0 ( echo heat.exe FAILED & pause & exit /b 1 )
echo OK

echo [3/5] candle.exe - compiling...
candle.exe "scripts\installer.wxs" "dist\ImageHosting.wxs" -nologo -dSourceDir="dist\ImageHosting" -dVersion=%VERSION% -out "dist\\"
if %ERRORLEVEL% neq 0 ( echo FAILED & pause & exit /b 1 )
echo OK

echo [4/5] light.exe - linking MSI...
light.exe "dist\installer.wixobj" "dist\ImageHosting.wixobj" -nologo -ext WixUIExtension -cultures:en-US -out "dist\ImageHosting-%VERSION%.msi"
if %ERRORLEVEL% neq 0 ( echo FAILED & pause & exit /b 1 )

echo [5/5] Cleaning up intermediate files...
if exist "build" rmdir /S /Q "build"
if exist "ImageHosting.spec" del /Q "ImageHosting.spec"
if exist "dist\ImageHosting" rmdir /S /Q "dist\ImageHosting"
if exist "dist\ImageHosting.wxs" del /Q "dist\ImageHosting.wxs"
del /Q "dist\*.wixobj" 2>nul
del /Q "dist\*.wixpdb" 2>nul
echo OK

echo.
echo SUCCESS - dist\ImageHosting-%VERSION%.msi
pause
endlocal
