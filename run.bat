@echo off
cd /d "%~dp0"

:: Check if virtual environment folder exists
if not exist venv (
    echo [System] Virtual environment not found. Creating venv...
    "C:\Python314\python.exe" -m venv venv
    if errorlevel 1 (
        echo [Error] Failed to create virtual environment. Ensure Python 3.14 is installed.
        pause
        exit /b 1
    )
    echo [System] Virtual environment created successfully.
)

:: Activate the virtual environment
echo [System] Activating virtual environment...
call venv\Scripts\activate.bat

:: Install and update dependencies within the venv
echo [System] Verifying and installing dependencies inside the venv...
python -m pip install --upgrade pip --quiet
python -m pip install discord.py telethon --quiet

:: Run the bridge bot script
echo [System] Starting bridge_bot.py...
python bridge_bot.py

pause
