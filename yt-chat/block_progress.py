#!/usr/bin/env python3
import time
import os
import sys
from mcrcon import MCRcon
from pathlib import Path
from filelock import FileLock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from env_loader import get_float_env, get_int_env, get_required_env, load_env_file

load_env_file(PROJECT_ROOT / ".env")

RCON_HOST     = os.getenv("RCON_HOST", "localhost")
RCON_PORT     = get_int_env("RCON_PORT", 25575)
RCON_PASSWORD = get_required_env("RCON_PASSWORD")
PLAYER        = os.getenv("PLAYER", "Player")
TARGET        = get_int_env("BLOCK_TARGET", 10_000_000)
SCORE_OFFSET  = get_int_env("SCORE_OFFSET", 9300000)
POLL_INTERVAL = get_float_env("BLOCK_POLL_INTERVAL", 1.0)

OUT_COUNT     = Path("blocks_count.txt")
OUT_PERCENT   = Path("blocks_percent.txt")

def parse_score(resp: str) -> int:
    # Risposta tipo: "EdoBaz has 12345 [broken]"
    parts = resp.split()
    for i,p in enumerate(parts):
        if p == "has" and i+1 < len(parts):
            try:
                return int(parts[i+1])
            except:
                pass
    # fallback: prova a trovare il primo numero nella stringa
    import re
    m = re.search(r"(\\d+)", resp or "")
    return int(m.group(1)) if m else 0

def write_with_lock(path: Path, text: str):
    lock = FileLock(str(path) + ".lock")
    with lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

def main():
    with MCRcon(RCON_HOST, RCON_PASSWORD, port=RCON_PORT) as mcr:
        while True:
            # interroga il punteggio "broken" (stone)
            resp = mcr.command(f"scoreboard players get {PLAYER} broken")
            count = parse_score(resp)
            # Keep compatibility with old setups that counted from an offset.
            count += SCORE_OFFSET

            # calcola percentuale
            percent = count / TARGET * 100 if TARGET else 0.0

            # scrive i file con lock per evitare letture parziali
            write_with_lock(OUT_COUNT, f"{count}\n")
            write_with_lock(OUT_PERCENT, f"{percent:.2f}%\n")

            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
