@echo off
chcp 65001 >nul
title Build VTP Fleet Tracking EXE
cd /d "%~dp0"

echo ==============================================================================
echo   TIEN TRINH DONG GOI VTP FLEET TRACKING THANH FILE .EXE CHO WINDOWS
echo ==============================================================================
echo.

REM Kiem tra moi truong Python
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [LOI] Khong tim thay Python trong PATH. Vui long cai dat Python 3.10+ truoc!
    pause
    exit /b 1
)

echo [1/3] Cai dat PyInstaller va cac thu vien can thiet...
python -m pip install --upgrade pip
python -m pip install pyinstaller fastapi uvicorn pydantic httpx openpyxl python-dotenv

echo [2/3] Dang bien dich thanh file exe doc lap bang PyInstaller...
pyinstaller --clean -y vtp_fleet.spec

echo [3/3] Hoan tat! File thuc thi duoc tao tai:
echo       dist\VTP_Fleet_Tracking.exe
echo.
pause
