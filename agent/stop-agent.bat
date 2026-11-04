@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

title CyberPrint Pay - Stop Agent

echo ========================================================
echo  CyberPrint Pay Agent ko band kiya ja raha hai...
echo ========================================================

REM 1. Terminate PID from agent.pid if exists
if exist "agent.pid" (
    set /p AGENT_PID=<"agent.pid"
    if defined AGENT_PID (
        taskkill /F /PID !AGENT_PID! >nul 2>&1
    )
    del /f /q "agent.pid" >nul 2>&1
)

REM 2. Safety cleanup: terminate any lingering pythonw / python running agent.py
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name LIKE 'python%'\" | Where-Object { $_.CommandLine -like '*agent.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

echo.
echo ========================================================
echo  CyberPrint Pay Agent safaltapoorvak band ho gaya hai.
echo ========================================================
ping 127.0.0.1 -n 3 >nul
