#!/usr/bin/env python3
import asyncio
import logging
import datetime
import os
import json
import time
import sys
from collections import deque
from kickpython import KickAPI as AsyncKickAPI
from kickapi    import KickAPI as SyncKickAPI
from filelock import FileLock
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from env_loader import get_int_env, get_required_env, load_env_file

load_env_file(PROJECT_ROOT / ".env")

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# --- Configuration ---
CHANNEL_SLUG         = os.getenv("KICK_CHANNEL_SLUG", "your-kick-channel")
COMMAND_FILE         = Path(os.getenv("COMMAND_FILE", "kick_commands.jsonl"))
LOG_FILE             = Path(os.getenv("LOG_FILE", "chat_log.txt"))
FOLLOW_FILE          = Path(os.getenv("FOLLOW_FILE", "follower_count.txt"))
FOLLOW_POLL_INTERVAL = get_int_env("FOLLOW_POLL_INTERVAL", 30)  # seconds
RECENT_COMMANDS      = Path(os.getenv("RECENT_COMMANDS", "recent_commands.txt"))

ALLOWED_COMMANDS = {
    "!boost",
    "!slow",
    "!speed",
    "!water",
    "!milk",
    "!fatigue",
    "!tnt",
}

# User cooldown (seconds)
USER_COOLDOWN = get_int_env("USER_COOLDOWN", 0)

KICK_CLIENT_ID = get_required_env("KICK_CLIENT_ID")
KICK_CLIENT_SECRET = get_required_env("KICK_CLIENT_SECRET")

# --- KickAPI (asynchronous) ---
async_api = AsyncKickAPI(
    client_id=KICK_CLIENT_ID,
    client_secret=KICK_CLIENT_SECRET,
    redirect_uri=os.getenv("KICK_REDIRECT_URI", "https://localhost/callback"),
    db_path=os.getenv("KICK_DB_PATH", "kick_tokens.db")
)

# --- In-memory state ---
last_command_times = {}  # user -> ts
recent_commands = deque(maxlen=50)

# --- File lock helpers ---

def atomic_append_jsonl(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(path) + ".lock")
    with lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

def atomic_write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(path) + ".lock")
    with lock:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

# --- Chat handler ---
async def on_message(message: dict):
    user = message.get("sender_username", "unknown")
    text = message.get("content", "")
    ts   = datetime.datetime.utcnow().isoformat() + "Z"

    # 1) Full chat log (append)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] [{user}]: {text}\n")

    # 2) Allowed commands: enqueue as JSONL with lock
    clean_text = text.strip().split()[0] if text.strip() else ""
    if clean_text in ALLOWED_COMMANDS:
        now = time.time()
        last = last_command_times.get(user, 0)
        if now - last < USER_COOLDOWN:
            logging.info(f"⏳ Ignoring command {clean_text} from {user} (cooldown)")
            return

        cmd_obj = {
            "command": clean_text,
            "user": user,
            "ts": ts,
        }
        atomic_append_jsonl(COMMAND_FILE, cmd_obj)
        last_command_times[user] = now

        # Keep recent command lines for overlay widgets
        recent_commands.appendleft(f"{ts} {user}: {clean_text}")
        atomic_write_text(RECENT_COMMANDS, "\n".join(recent_commands))

    # --- Chat listener coroutine ---
async def listen_to_chat():
    async_api.add_message_handler(on_message)
    await async_api.connect_to_chatroom(CHANNEL_SLUG)

# --- Helper to run sync API call in thread ---
async def get_followers_count_threaded(sync_api, channel_slug):
    def _get():
        ch = sync_api.channel(channel_slug)
        return getattr(ch, "followers", 0)
    return await asyncio.to_thread(_get)

# --- Follower polling coroutine ---
async def poll_new_followers():
    # Read last_count from file (atomic)
    if FOLLOW_FILE.exists():
        try:
            last_count = int(FOLLOW_FILE.read_text().strip())
        except Exception:
            last_count = None
    else:
        last_count = None

    sync_api = SyncKickAPI()

    while True:
        try:
            count = await get_followers_count_threaded(sync_api, CHANNEL_SLUG)

            if last_count is None:
                last_count = count
                atomic_write_text(FOLLOW_FILE, str(count))

            elif count > last_count:
                diff = count - last_count
                logging.info(f"🔔 +{diff} follower (total {count})")
                atomic_write_text(FOLLOW_FILE, str(count))

                # Post thank-you message in chat
                try:
                    await async_api.post_chat(
                        f"🎉 Thanks for {diff} new followers! Total: {count} 🙏"
                    )
                except Exception:
                    logging.exception("Failed to send chat message")

                # Queue !eff for each follower (with a safety cap)
                for _ in range(min(diff, 20)):
                    cmd_obj = {"command": "!eff", "user": "system_follower", "ts": datetime.datetime.utcnow().isoformat() + "Z"}
                    atomic_append_jsonl(COMMAND_FILE, cmd_obj)

                last_count = count

        except Exception:
            logging.exception("❌ Follower polling error")

        await asyncio.sleep(FOLLOW_POLL_INTERVAL)

# --- Main function ---
async def main():
    await async_api.start_token_refresh()
    logging.info(f"🎧 Starting bot for {CHANNEL_SLUG}…")

    await asyncio.gather(
        listen_to_chat(),
        poll_new_followers(),
        asyncio.Event().wait()
    )

# --- Startup ---
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped.")