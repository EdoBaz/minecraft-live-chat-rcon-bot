<div align="center">

# Minecraft Live Chat RCON Bot

**Live chat integration for Minecraft servers via RCON protocol**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Minecraft](https://img.shields.io/badge/Minecraft-1.20.1%20%7C%201.21-62B47A?style=for-the-badge&logo=minecraft&logoColor=white)](https://minecraft.net)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

Connect Kick or YouTube live chat to your Minecraft server. Viewers can control gameplay through chat commands while the bot manages pickaxe upgrades based on follower count and updates OBS overlays in real-time.

</div>

---

## Features

- **Chat Commands** - Processes viewer commands (`!boost`, `!slow`, `!speed`, `!water`, `!milk`, `!fatigue`, `!tnt`)
- **RCON Integration** - Sends commands to Minecraft server via RCON protocol
- **Atomic Queue System** - Thread-safe command queuing with file locks
- **Auto Upgrades** - Automatic pickaxe and efficiency upgrades based on follower/subscriber count
- **OBS Overlays** - Real-time overlay updates for streaming (block progress, pickaxe tier, countdown)
- **TNT Rain** - System command for scheduled TNT events with countdown timer (YouTube mode)

---

## Demo

Command examples:

| Command | Effect | Preview |
|---------|--------|---------|
| `!boost` | Mining speed boost | ![boost](assets/video/boost.gif) |
| `!tnt` | Single TNT explosion | ![tnt](assets/video/tnt.gif) |
| `!!tnt_rain` | TNT rain with countdown | ![tntrain](assets/video/TNTrain.gif) |

---

## Supported Platforms

| Platform | Startup Script | Requirements |
|----------|---------------|--------------|
| Kick | `start_all.bat` | OAuth credentials |
| YouTube | `start_youtube.bat` | StreamElements webhook + OAuth (optional) |

---

## Chat Commands

### Viewer Commands

| Command | Effect |
|---------|--------|
| `!boost` | Boost effect |
| `!slow` | Slow effect |
| `!speed` | Speed effect |
| `!water` | Water effect |
| `!milk` | Milk effect |
| `!fatigue` | Fatigue effect |
| `!tnt` | TNT explosion |

### Operational Notes

> **Kick Mode**
> - Commands come from the channel configured in `KICK_CHANNEL_SLUG`
> - Only the first word of the message is parsed (e.g., `!tnt now` → `!tnt`)

> **YouTube Mode**
> - Commands received through StreamElements webhook: `GET /command?name=...`
> - Port configured via `SE_WEBHOOK_PORT`
> - `!!tnt_rain` is reserved for system/admin scripts only

---

## Requirements

| Component | Version |
|-----------|---------|
| Windows | 10/11 with PowerShell |
| Python | 3.11+ |
| Java | 17+ |
| Minecraft Server | 1.20.1 or 1.21 with RCON enabled |

**Note:** Startup scripts reference `server/server.jar`. For different Minecraft versions, ensure the server jar is located at this path.

---

## Installation

### 1. Create Virtual Environment

```bat
python -m venv .venv
```

**Activation:**
| Shell | Command |
|-------|---------|
| CMD | `.venv\Scripts\activate.bat` |
| PowerShell | `.\.venv\Scripts\Activate.ps1` |

### 2. Install Dependencies

```bat
pip install -r requirements.txt
```

### 3. Configure Environment

```bat
copy .env.example .env
```

### 4. Fill `.env` with Required Values

| Variable | Required For |
|----------|--------------|
| `RCON_PASSWORD` | All modes |
| `PLAYER` | All modes |
| `KICK_CLIENT_ID` | Kick mode |
| `KICK_CLIENT_SECRET` | Kick mode |
| `KICK_CHANNEL_SLUG` | Kick mode |
| `YT_CHANNEL_ID` | YouTube mode |

### 5. YouTube OAuth (YouTube mode only)

```bat
copy yt-chat\oauth2_client.example.json yt-chat\oauth2_client.json
```

Insert real Google OAuth `client_id` and `client_secret`. On first run, `yt-chat/yt_token.pickle` will be created locally.

---

## Minecraft Server Setup

Server and mod folders are excluded from version control to keep the repository lightweight.

### Server Configuration

1. Create `server/` folder in project root
2. Place Minecraft `server.jar` inside `server/`
3. Run server once to generate configuration files
4. Accept EULA by setting `eula=true` in `server/eula.txt`
5. Configure RCON in `server/server.properties`

### RCON Configuration

Add these lines to `server/server.properties`:

```properties
enable-rcon=true
rcon.port=25575
rcon.password=YOUR_STRONG_PASSWORD
```

**Important:** Ensure `RCON_PASSWORD` in `.env` matches `rcon.password` in server properties.

---

## Client Mods

Server integration does not require server-side mods. For continuous mining on the player client, use Fabric with:

| Mod | Required |
|-----|----------|
| Baritone standalone | Yes |
| Fabric API | Yes |
| Cloth Config | Yes |
| Gamma Utils | Yes |
| ModMenu | No |
| StreamerCraft | No |
| EffectMC | No |

Mod folders (`mod1.20.1/`, `mod1.21/`) are excluded from Git. See `settingBaritone.txt` for Baritone configuration reference.

---

## Platform Configuration

### Kick

Required environment variables:

| Variable | Description |
|----------|-------------|
| `KICK_CHANNEL_SLUG` | Channel slug |
| `KICK_CLIENT_ID` | OAuth client ID |
| `KICK_CLIENT_SECRET` | OAuth client secret |

**Note:** The `!eff` command is generated automatically by follower logic and is not a viewer command.

### YouTube / StreamElements

Required environment variables:

| Variable | Description |
|----------|-------------|
| `YT_CHANNEL_ID` | YouTube channel ID |
| `SE_WEBHOOK_HOST` | Webhook host address |
| `SE_WEBHOOK_PORT` | Webhook port (default: 8080) |

**OAuth Setup:**
1. Copy `yt-chat/oauth2_client.example.json` to `yt-chat/oauth2_client.json`
2. Insert OAuth credentials from Google Cloud Console
3. Complete browser authentication on first run

**StreamElements Integration:**
- Webhook endpoint: `GET /command?name=<command>`
- For remote access, expose port using port forwarding or tunneling (ngrok/cloudflared)
- Set `YOUTUBE_API_NEEDED=false` to disable subscriber polling and use webhook-only mode

---

## Usage

### Pre-startup Checklist

- `server/server.jar` exists
- `.env` configured with `RCON_PASSWORD`, `PLAYER`, and platform credentials
- RCON enabled in `server/server.properties`
- Scoreboard objective `broken` created in-game
- (YouTube only) `oauth2_client.json` configured if using API polling

### Kick Mode

```bat
start_all.bat
```

Starts four processes:
- Minecraft server
- Kick chat listener
- RCON command processor
- Block progress monitor

### YouTube Mode

```bat
start_youtube.bat
```

Starts four processes:
- Minecraft server
- YouTube webhook server
- RCON command processor
- Block progress monitor

---

## In-Game Setup

Create the block mining scoreboard with these commands:

```mcfunction
/scoreboard objectives add broken minecraft.mined:minecraft.stone
/scoreboard objectives setdisplay sidebar broken
```

---

## OBS Overlays

Overlay HTML files are located in:

| Platform | Path |
|----------|------|
| Kick | `kick-chat/overlay/` |
| YouTube | `yt-chat/overlay/` |

Overlays automatically read state files generated by the bot processes.

---


## Notes

- Missing `server/server.jar` will trigger startup error
- Missing required environment variables will halt execution with error message
- Missing Python dependencies can be reinstalled with `pip install -r requirements.txt`

---

## License

MIT License - see [LICENSE](LICENSE) file for details.

---
