@echo off
cd /d "%~dp0"
echo Killing old processes on port 8000 and 5173...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do taskkill /F /PID %%a 2>nul
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173" ^| findstr "LISTENING"') do taskkill /F /PID %%a 2>nul
timeout /t 1 /nobreak >nul
echo Cleaning Python cache...
for /d /r "%~dp0" %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>nul
echo Starting fresh...
python start.py
pause
