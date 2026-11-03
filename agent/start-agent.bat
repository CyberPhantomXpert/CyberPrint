@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

title CyberPrint Pay - Agent Launcher

REM 1. Check if agent is already running
if exist "agent.pid" (
    set /p CUR_PID=<"agent.pid"
    if defined CUR_PID (
        tasklist /FI "PID eq !CUR_PID!" 2>nul | findstr /i "!CUR_PID!" >nul
        if not errorlevel 1 (
            echo ========================================================
            echo  CyberPrint Pay Agent pehle se background mein chal raha hai!
            echo  Process ID: !CUR_PID!
            echo ========================================================
            echo.
            echo  - Agar restart karna hai toh pehle stop-agent.bat chalayein.
            echo  - Agent ko band karne ke liye stop-agent.bat chalayein.
            echo.
            ping 127.0.0.1 -n 4 >nul
            exit /b 0
        )
    )
    del /f /q "agent.pid" >nul 2>&1
)

REM 2. Launch agent in background with pythonw (with auto-fallback)
start "" pythonw "agent.py"

REM 3. Wait up to 6 seconds for PID file to appear
set ATTEMPTS=0
:WAIT_LOOP
ping 127.0.0.1 -n 2 >nul
if exist "agent.pid" goto :STARTED
set /a ATTEMPTS+=1
if !ATTEMPTS! lss 4 goto :WAIT_LOOP

REM If pythonw did not create agent.pid, fallback to minimized python console
if not exist "agent.pid" (
    start /min "CyberPrint Pay Agent" python "agent.py"
    ping 127.0.0.1 -n 3 >nul
)

:STARTED
if exist "agent.pid" (
    set /p NEW_PID=<"agent.pid"
    echo ========================================================
    echo  CyberPrint Pay - Agent Background Mein Chalu Ho Gaya!
    echo ========================================================
    echo  Process ID       : !NEW_PID!
    echo  Mode             : Silent Background
    echo.
    echo  - Koi black terminal open rakhne ki zaroorat nahi hai.
    echo  - Naya print aane par screen popup aur sound alert aayega.
    echo  - Agent ko band karne ke liye stop-agent.bat chalayein.
    echo ========================================================
    ping 127.0.0.1 -n 4 >nul
    exit /b 0
) else (
    echo ========================================================
    echo  WARNING: Agent background mein shuru nahi ho saka!
    echo ========================================================
    echo  Kripya agent.log check karein ya run-agent.bat chala kar
    echo  error dekhein.
    echo ========================================================
    echo.
    if exist "agent.log" (
        echo --- Aakhri log entries: ---
        powershell -NoProfile -Command "Get-Content agent.log -Tail 5"
    )
    echo.
    pause
    exit /b 1
)
