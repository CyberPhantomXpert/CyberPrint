@echo off
cd /d "%~dp0"
title CyberPrint Pay - Agent Console
echo ========================================================
echo  CyberPrint Pay Agent (Console Mode)
echo ========================================================
echo  Agar background mein chalana hai toh 'start-agent.bat' chalayein.
echo.
python "agent.py"
pause
