#!/usr/bin/env python3
import time
import logging
import os
import sys
from pathlib import Path
import threading
from flask import Flask, request
from filelock import FileLock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from env_loader import get_bool_env, get_int_env, load_env_file

load_env_file(PROJECT_ROOT / ".env")

# --- Configuration ---
YOUTUBE_API_NEEDED = get_bool_env("YOUTUBE_API_NEEDED", True)
OAUTH_CLIENT_JSON = os.getenv("OAUTH_CLIENT_JSON", "oauth2_client.json")
TOKEN_PICKLE      = os.getenv("TOKEN_PICKLE", "yt_token.pickle")
CHANNEL_ID        = os.getenv("YT_CHANNEL_ID", "")
POLL_INTERVAL_MIN = get_int_env("YT_POLL_INTERVAL_MIN", 5)
SE_WEBHOOK_HOST   = os.getenv("SE_WEBHOOK_HOST", "0.0.0.0")
SE_WEBHOOK_PORT   = get_int_env("SE_WEBHOOK_PORT", 8080)
YT_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
# ---------------------

# --- Output files ---
BASE_DIR = Path(__file__).parent
YT_COMMAND_FILE  = BASE_DIR / "yt_commands.txt"
YT_FOLLOWER_FILE = BASE_DIR / "yt_follower_count.txt"
# --------------------

# Allowed commands (include the exclamation mark)
ALLOWED_COMMANDS = {"!eff","!boost","!slow","!speed",
                    "!water","!milk","!fatigue","!tnt"}

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- StreamElements Flask webhook ---
app = Flask(__name__)

@app.route("/command", methods=["GET"])
def se_command():
    raw = request.args.get("name", "").strip()
    # Normalize command by adding '!' when missing
    cmd = raw if raw.startswith("!") else f"!{raw}"
    logging.info(f"📥 Request received: raw={raw}, normalized={cmd}")
    if cmd in ALLOWED_COMMANDS:
        try:
            # Use FileLock for safe append operations
            lock = FileLock(str(YT_COMMAND_FILE) + ".lock")
            with lock:
                # Ensure parent folder exists
                YT_COMMAND_FILE.parent.mkdir(parents=True, exist_ok=True)
                with YT_COMMAND_FILE.open("a", encoding="utf-8") as f:
                    f.write(cmd + "\n")
            logging.info(f"🏷️ Command queued: {cmd}")
        except Exception as e:
            logging.error(f"❌ File write error: {e}")
    else:
        logging.warning(f"⚠️ Command not allowed: {cmd}")
    return "", 204

# --- YouTube API follower polling ---
if YOUTUBE_API_NEEDED:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
    import pickle

    def init_youtube_api():
        client_path = Path(OAUTH_CLIENT_JSON)
        if not client_path.exists():
            raise RuntimeError(
                f"Missing OAuth client file: {client_path}. "
                "Copy yt-chat/oauth2_client.example.json to oauth2_client.json and fill your credentials."
            )

        creds = None
        if Path(TOKEN_PICKLE).exists():
            with open(TOKEN_PICKLE, "rb") as f:
                creds = pickle.load(f)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    OAUTH_CLIENT_JSON,
                    YT_SCOPES,
                )
                creds = flow.run_local_server(host="localhost", port=0)
            with open(TOKEN_PICKLE, "wb") as f:
                pickle.dump(creds, f)
        return build("youtube", "v3", credentials=creds)

    def poll_followers():
        youtube = init_youtube_api()
        last_count = None
        while True:
            try:
                resp = youtube.channels().list(part="statistics", id=CHANNEL_ID).execute()
                count = int(resp["items"][0]["statistics"].get("subscriberCount", 0))
                if last_count is None or count != last_count:
                    try:
                        # Write safely with FileLock
                        lock = FileLock(str(YT_FOLLOWER_FILE) + ".lock")
                        with lock:
                            YT_FOLLOWER_FILE.parent.mkdir(parents=True, exist_ok=True)
                            YT_FOLLOWER_FILE.write_text(str(count), encoding="utf-8")
                        logging.info(f"🔔 Subscriber count updated: {count}")
                    except Exception as e:
                        logging.error(f"❌ Follower file write error: {e}")
                    last_count = count
                time.sleep(POLL_INTERVAL_MIN * 60)
            except Exception as e:
                logging.error(f"❌ Subscriber polling error: {e}")
                time.sleep(POLL_INTERVAL_MIN * 60)

# Flask server startup

def start_webhook():
    logging.info("🚀 Starting Flask server on %s:%s", SE_WEBHOOK_HOST, SE_WEBHOOK_PORT)
    app.run(host=SE_WEBHOOK_HOST, port=SE_WEBHOOK_PORT, debug=False)

def main():
    if YOUTUBE_API_NEEDED and not CHANNEL_ID:
        raise RuntimeError("Missing required environment variable: YT_CHANNEL_ID")

    # Start StreamElements webhook
    threading.Thread(target=start_webhook, daemon=True).start()

    # Start subscriber polling if enabled
    if YOUTUBE_API_NEEDED:
        threading.Thread(target=poll_followers, daemon=True).start()

    logging.info("🛡️ Bot running. Waiting for SE commands and subscriber polling...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("👋 Bot stopped by user.")

if __name__ == "__main__":
    main()
