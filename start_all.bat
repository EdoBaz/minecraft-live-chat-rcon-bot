@echo off
title ProgettoBOT Full Startup

if not exist "%~dp0server\server.jar" (
  echo [ERROR] server\server.jar not found.
  echo Create the server folder and place the Minecraft server jar inside it.
  pause
  exit /b 1
)

if not exist "%~dp0.env" (
  echo [ERROR] .env file not found in the project root.
  echo Copy .env.example to .env and fill in the required variables.
  pause
  exit /b 1
)

set "PYTHON_BIN=python"
if exist "%~dp0.venv\Scripts\python.exe" (
  set "PYTHON_BIN=%~dp0.venv\Scripts\python.exe"
)

:: 1) Start the Minecraft server
start "MC Server" cmd /k ^
  "cd /d \"%~dp0server\" && ^
   java -Xmx2G -Xms1G -jar server.jar nogui"

:: 2) Start the chat + follower bot
start "ChatBot" cmd /k ^
  "cd /d \"%~dp0kick-chat\" && ^
  \"%PYTHON_BIN%\" script.py"

:: 3) Start the RCON controller (chat commands -> Minecraft)
start "RCON Bot" cmd /k ^
  "cd /d \"%~dp0kick-chat\" && ^
  \"%PYTHON_BIN%\" mc_rcon_control.py"

:: 4) Start the block progress monitor (blocks_count.txt + percent)
start "BlockProgress" cmd /k ^
  "cd /d \"%~dp0kick-chat\" && ^
  \"%PYTHON_BIN%\" block_progress.py"

echo All processes have been started.
pause
