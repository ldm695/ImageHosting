@echo off
cd /d "%~dp0.."

pyinstaller ^
  --onedir ^
  --name ImageHosting ^
  --icon "assets\icon.ico" ^
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --add-data "assets\icon.ico;." ^
  --hidden-import PIL ^
  --hidden-import pystray ^
  --noconsole ^
  --clean ^
  app.py
