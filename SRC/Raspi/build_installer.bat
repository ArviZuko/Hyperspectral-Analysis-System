@echo off
cd /d "%~dp0"
call "build installer.bat"
exit /b %errorlevel%
