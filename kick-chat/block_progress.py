#!/usr/bin/env python3
import time
import re
import logging
import os
import sys
from pathlib import Path
from mcrcon import MCRcon

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from env_loader import get_float_env, get_int_env, get_required_env, load_env_file

load_env_file(PROJECT_ROOT / ".env")

# config
RCON_HOST = os.getenv("RCON_HOST", "localhost")
RCON_PORT = get_int_env("RCON_PORT", 25575)
RCON_PASSWORD = get_required_env("RCON_PASSWORD")
PLAYER = os.getenv("PLAYER", "Player")
TARGET = get_int_env("BLOCK_TARGET", 1_000_000)
POLL_INTERVAL = get_float_env("BLOCK_POLL_INTERVAL", 1.0)  # seconds
OUT_COUNT = Path("blocks_count.txt")
OUT_PERCENT = Path("blocks_percent.txt")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

score_re = re.compile(r"has\s+(\d+)")

def parse_score(resp: str) -> int:
    m = score_re.search(resp or "")
    return int(m.group(1)) if m else 0


def main():
    with MCRcon(RCON_HOST, RCON_PASSWORD, port=RCON_PORT) as mcr:
        logging.info("Connected to RCON for progress polling")
        while True:
            resp = mcr.command(f"scoreboard players get {PLAYER} broken")
            count = parse_score(resp)
            percent = (count / TARGET) * 100 if TARGET else 0.0

            OUT_COUNT.write_text(f"{count}\n", encoding="utf-8")
            OUT_PERCENT.write_text(f"{percent:.4f}%\n", encoding="utf-8")

            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()