# Digging Bot LIVE Project

Live chat interaction system -> Minecraft.

This project connects chat commands (Kick or YouTube/StreamElements) to a local Minecraft server through RCON, updates local state files, and powers HTML overlays for OBS.

## What It Does

- Receives chat commands (`!boost`, `!slow`, `!speed`, `!water`, `!milk`, `!fatigue`, `!tnt`).
- Queues commands into local files atomically (with file locks).
- Consumes the queue and sends Minecraft commands via RCON.
- Handles pickaxe and efficiency upgrades based on follower/subscriber count.
- Updates block progress files for OBS overlays.
- In YouTube mode, also supports the `!!tnt_rain` system trigger with countdown.

## Supported Modes

- Kick mode: `start_all.bat`
- YouTube mode: `start_youtube.bat`

## Chat Commands (Kick and YouTube)

Supported viewer commands:

- `!boost`
- `!slow`
- `!speed`
- `!water`
- `!milk`
- `!fatigue`
- `!tnt`

Operational notes:

- In Kick mode, commands come from the channel configured in `KICK_CHANNEL_SLUG`.
- In Kick mode, only the first word of the message is parsed (example: `!tnt now` is treated as `!tnt`).
- In YouTube mode, commands are received through a StreamElements webhook on `GET /command?name=...` (port set by `SE_WEBHOOK_PORT`).
- The special command `!!tnt_rain` is reserved for system/admin scripts, not standard viewers.

## Requirements

- Windows + PowerShell/CMD
- Python 3.11+
- Java 17+
- Local Minecraft server with RCON enabled

## Tested Versions

- Minecraft server: 1.20.1 and 1.21
- Java: 17+
- Python: 3.11+
- OS tested: Windows

Important note:

- Startup scripts always use `server/server.jar`.
- If you use 1.21 (or another version), place that server jar at `server/server.jar`.

## Installation

1. Create a Python virtual environment (recommended):

```bat
python -m venv .venv
```

Virtual environment activation:

- CMD: `.venv\Scripts\activate.bat`
- PowerShell: `.\.venv\Scripts\Activate.ps1`

2. Install dependencies:

```bat
pip install -r requirements.txt
```

3. Create the environment file:

```bat
copy .env.example .env
```

4. Fill `.env` with your real values (at minimum):

- `RCON_PASSWORD`
- `PLAYER`
- `KICK_CLIENT_ID`
- `KICK_CLIENT_SECRET`
- `KICK_CHANNEL_SLUG`
- `YT_CHANNEL_ID` (if using YouTube mode)

5. YouTube OAuth (YouTube mode only):

- Copy `yt-chat/oauth2_client.example.json` to `yt-chat/oauth2_client.json`
- Insert real Google OAuth `client_id` and `client_secret`
- On first run, `yt-chat/yt_token.pickle` will be created locally

## Local Minecraft Server Setup

Server/mod folders are excluded from version control (`.gitignore`) to keep the repository lightweight.

Quick setup from scratch:

1. Create a `server/` folder in the project root.
2. Put `server.jar` inside `server/`.
3. Run the server once to generate base files.
4. Set `eula=true` in `server/eula.txt`.
5. Configure RCON in `server/server.properties`.

Minimum recommended `server/server.properties` config:

```properties
enable-rcon=true
rcon.port=25575
rcon.password=YOUR_STRONG_PASSWORD
```

Make sure `RCON_PASSWORD` in `.env` matches `rcon.password`.

## Client Mods (for Continuous Mining)

Chat and RCON integration does not require mandatory server mods.

To keep mining continuously on the player client, use a Fabric client with mods such as:

- Baritone standalone
- Fabric API
- Cloth Config
- Gamma Utils
- Optional: ModMenu, StreamerCraft, EffectMC

Local folders `mod1.20.1/` and `mod1.21/` are examples of your environment and are not meant to be pushed to Git.

Use `settingBaritone.txt` as a quick reference for Baritone settings/commands.

## Kick Configuration

Minimum required `.env` variables:

- `KICK_CHANNEL_SLUG`
- `KICK_CLIENT_ID`
- `KICK_CLIENT_SECRET`

Important behavior:

- Kick bot accepts only whitelisted commands.
- `!eff` is not a viewer command. It is generated only by follower logic.

## YouTube / StreamElements Configuration

Minimum required `.env` variables:

- `YT_CHANNEL_ID`
- `SE_WEBHOOK_HOST`
- `SE_WEBHOOK_PORT`

YouTube OAuth:

1. Copy `yt-chat/oauth2_client.example.json` to `yt-chat/oauth2_client.json`.
2. Add real OAuth credentials in the copied file.
3. Complete browser consent on first startup.

StreamElements webhook:

- Bot endpoint: `GET /command?name=<command>` on `SE_WEBHOOK_PORT`.
- If bot runs locally and StreamElements is remote, expose the port with port forwarding or a tunnel (for example ngrok/cloudflared).
- If you only want webhook commands (without subscriber polling), set `YOUTUBE_API_NEEDED=false` in `.env`.

## Start

Checklist before startup:

- `server/server.jar` exists
- `.env` is filled (`RCON_PASSWORD`, `PLAYER`, required Kick/YouTube values)
- `server/server.properties` has RCON enabled
- `broken` scoreboard objective has been created in game
- (YouTube) `yt-chat/oauth2_client.json` exists if `YOUTUBE_API_NEEDED=true`

### Kick

```bat
start_all.bat
```

This starts:

- local Minecraft server (`server/server.jar`)
- Kick bot (`kick-chat/script.py`)
- Kick RCON controller (`kick-chat/mc_rcon_control.py`)
- block progress monitor (`kick-chat/block_progress.py`)

### YouTube

```bat
start_youtube.bat
```

This starts:

- local Minecraft server (`server/server.jar`)
- YouTube/webhook bot (`yt-chat/yt_chat_bot.py`)
- YouTube RCON controller (`yt-chat/mc_rcon_control.py`)
- block progress monitor (`yt-chat/block_progress.py`)

## First In-Game Setup (block scoreboard)

Run these once in Minecraft:

```mcfunction
/scoreboard objectives add broken minecraft.mined:minecraft.stone
/scoreboard objectives setdisplay sidebar broken
```

## OBS Overlays

Use files under:

- `kick-chat/overlay/`
- `yt-chat/overlay/`

Overlays read state files generated automatically by the scripts.

## Security

This repository is prepared for publication:

- Secrets/tokens removed from source files
- Sensitive config read from environment variables (`.env`)
- Token/credential artifacts excluded by `.gitignore`
- Local server and heavy folders excluded from Git


## Useful Notes

- If `server/server.jar` is missing, startup scripts show an explicit error.
- If a required `.env` variable is missing, scripts stop with a clear error.
- If Python modules are missing, rerun `pip install -r requirements.txt` in the active environment.
