#!/usr/bin/env python3
"""
mc_rcon_control.py
Cross-platform version using filelock.FileLock.
"""
import time
import logging
import datetime
import os
import json
import sys
from pathlib import Path
from filelock import FileLock
from mcrcon import MCRcon

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from env_loader import get_float_env, get_int_env, get_required_env, load_env_file

load_env_file(PROJECT_ROOT / ".env")

# --- Config (env-friendly defaults) ---
RCON_HOST = os.getenv("RCON_HOST", "localhost")
RCON_PORT = get_int_env("RCON_PORT", 25575)
RCON_PASSWORD = get_required_env("RCON_PASSWORD")
PLAYER = os.getenv("PLAYER", "Player")
POLL_INTERVAL = get_float_env("POLL_INTERVAL", 5.0)
COMMAND_LIMIT = get_int_env("COMMAND_LIMIT", 3)

# files
FILE_FOLLOWERS = Path(os.getenv("FILE_FOLLOWERS", "follower_count.txt"))
FILE_EFF_LEVEL = Path(os.getenv("FILE_EFF_LEVEL", "eff_level.txt"))
FILE_CURRENT_PICK = Path(os.getenv("FILE_CURRENT_PICK", "current_pickaxe.txt"))
POLL_FILE = Path(os.getenv("POLL_FILE", "kick_commands.jsonl"))
HISTORY = Path(os.getenv("PROCESSED_HISTORY", "processed_commands.log"))

THRESHOLDS = [
    (5000, "netherite"),
    (2500, "diamond"),
    (1500, "golden"),
    (500,  "iron"),
    (100,  "stone"),
    (-1,    "wooden"),
]

CLEANUP_INTERVAL_MINUTES = get_int_env("CLEANUP_INTERVAL_MINUTES", 15)
CLEANUP_COMMAND = '/kill @e[type=minecraft:item,nbt={Item:{id:"minecraft:cobblestone"}}]'

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("mc_rcon_control")


# --- file helpers using FileLock (cross-platform) ---
def read_jsonl_and_clear(path: Path):
    """Read JSONL queue and truncate file atomically using a FileLock.
    Returns a list of dicts (possibly empty).
    """
    items = []
    lock = FileLock(str(path) + ".lock")
    with lock:
        if not path.exists():
            return items
        with path.open("r+", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except Exception:
                    logger.exception("decode jsonl line")
            # truncate after read
            f.seek(0)
            f.truncate()
    return items


def write_jsonl_atomic(path: Path, items):
    """Overwrite path with JSONL items atomically using FileLock."""
    lock = FileLock(str(path) + ".lock")
    with lock:
        with path.open("w", encoding="utf-8") as f:
            for itm in items:
                f.write(json.dumps(itm, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())


def append_history(text: str):
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(HISTORY) + ".lock")
    with lock:
        with HISTORY.open("a", encoding="utf-8") as f:
            f.write(text + "\n")
            f.flush()
            os.fsync(f.fileno())


# --- helpers ---
def pickaxe_for_followers(count: int) -> str:
    for thr, mat in THRESHOLDS:
        if count >= thr:
            return mat
    return THRESHOLDS[-1][1]


def send_rcon(mcr, cmd: str):
    try:
        resp = mcr.command(cmd)
        logger.info("> %s\n< %s", cmd, resp)
    except Exception:
        logger.exception("rcon send failed")
        # keep loop alive (do not re-raise)


# --- main ---
def ensure_files():
    if not FILE_CURRENT_PICK.exists():
        FILE_CURRENT_PICK.write_text(pickaxe_for_followers(0), encoding="utf-8")
    if not FILE_FOLLOWERS.exists():
        FILE_FOLLOWERS.write_text("0", encoding="utf-8")
    if not FILE_EFF_LEVEL.exists():
        FILE_EFF_LEVEL.write_text("0", encoding="utf-8")


def main():
    ensure_files()
    logger.info("Starting mc_rcon_control (FileLock)")
    last_cleanup = datetime.datetime.utcnow()

    while True:
        try:
            logger.info("Attempting RCON connect to %s:%s", RCON_HOST, RCON_PORT)
            with MCRcon(RCON_HOST, RCON_PASSWORD, port=RCON_PORT) as mcr:
                logger.info("RCON connected")
                while True:
                    # read state tolerant to missing/corrupt files
                    try:
                        followers = int(FILE_FOLLOWERS.read_text().strip())
                    except Exception:
                        followers = 0
                    current_pick = FILE_CURRENT_PICK.read_text().strip() if FILE_CURRENT_PICK.exists() else pickaxe_for_followers(0)
                    try:
                        eff_level = int(FILE_EFF_LEVEL.read_text().strip())
                    except Exception:
                        eff_level = 0

                    # periodic cleanup
                    now = datetime.datetime.utcnow()
                    if (now - last_cleanup).total_seconds() >= CLEANUP_INTERVAL_MINUTES * 60:
                        logger.info("Cleaning ground drops")
                        send_rcon(mcr, CLEANUP_COMMAND)
                        last_cleanup = now

                    # update pickaxe based on followers
                    new_pick = pickaxe_for_followers(followers)
                    if new_pick != current_pick:
                        logger.info("Change pick: %s -> %s", current_pick, new_pick)
                        send_rcon(mcr, f"item replace entity {PLAYER} weapon.mainhand with air")
                        # build NBT separately to avoid f-string brace issues
                        nbt0 = '{Unbreakable:1b,Enchantments:[{id:\"minecraft:efficiency\",lvl:0s}]}'
                        cmd = f"item replace entity {PLAYER} weapon.mainhand with minecraft:{new_pick}_pickaxe{nbt0}"
                        send_rcon(mcr, cmd)
                        FILE_CURRENT_PICK.write_text(new_pick, encoding="utf-8")
                        FILE_EFF_LEVEL.write_text("0", encoding="utf-8")
                        eff_level = 0

                    # increase efficiency gradually
                    base_thr = 0
                    for thr, _ in THRESHOLDS:
                        if followers >= thr:
                            base_thr = thr
                            break
                    target_eff = max(0, followers - base_thr)
                    if eff_level < target_eff:
                        eff_level += 1
                        logger.info("Set efficiency lvl %s", eff_level)
                        nbt_eff = '{Unbreakable:1b,Enchantments:[{id:"minecraft:efficiency",lvl:' + str(eff_level) + '}]}'
                        cmd = f"item replace entity {PLAYER} weapon.mainhand with minecraft:{new_pick}_pickaxe{nbt_eff}"
                        send_rcon(mcr, cmd)
                        FILE_EFF_LEVEL.write_text(str(eff_level), encoding="utf-8")

                    # process commands (JSONL) up to limit
                    queue = read_jsonl_and_clear(POLL_FILE)
                    if queue:
                        logger.info("Found %d commands", len(queue))

                    # take up to COMMAND_LIMIT now, put remaining back (so we keep order)
                    commands_to_process = queue[:COMMAND_LIMIT]
                    remaining = queue[COMMAND_LIMIT:]
                    if remaining:
                        write_jsonl_atomic(POLL_FILE, remaining)

                    for item in commands_to_process:
                        cmd_key = item.get("command")
                        user = item.get("user")
                        if not cmd_key:
                            continue

                        # whitelist actions
                        if cmd_key == "!boost":
                            send_rcon(mcr, f"effect give {PLAYER} haste 10 2")
                        elif cmd_key == "!slow":
                            send_rcon(mcr, f"effect give {PLAYER} slowness 10 1")
                        elif cmd_key == "!speed":
                            send_rcon(mcr, f"effect give {PLAYER} speed 10 1")
                        elif cmd_key == "!water":
                            send_rcon(mcr, f"execute as {PLAYER} at {PLAYER} run setblock ~ ~-1 ~ water")
                        elif cmd_key == "!milk":
                            send_rcon(mcr, f"effect clear {PLAYER}")
                        elif cmd_key == "!fatigue":
                            send_rcon(mcr, f"effect give {PLAYER} mining_fatigue 10 1")
                        elif cmd_key == "!tnt":
                            tnt_nbt = "{Fuse:1}"
                            send_rcon(mcr, f"execute as {PLAYER} at {PLAYER} run summon tnt ~ ~-1 ~ {tnt_nbt}")

                        elif cmd_key == "!eff":
                            # ONLY accept !eff when generated by the follower-polling system
                            if user == "system_follower":
                                eff_level += 1
                                nbt_eff = '{Unbreakable:1b,Enchantments:[{id:"minecraft:efficiency",lvl:' + str(eff_level) + '}]}'
                                send_rcon(mcr, f"item replace entity {PLAYER} weapon.mainhand with minecraft:{new_pick}_pickaxe{nbt_eff}")
                                FILE_EFF_LEVEL.write_text(str(eff_level), encoding="utf-8")
                                append_history(f"{datetime.datetime.utcnow().isoformat()}Z {user} {cmd_key}")
                            else:
                                logger.info("Ignored !eff from chat user %s", user)
                                append_history(f"{datetime.datetime.utcnow().isoformat()}Z {user} IGNORED {cmd_key}")
                        else:
                            logger.info("Unknown command from chat: %s by %s", cmd_key, user)
                            append_history(f"{datetime.datetime.utcnow().isoformat()}Z {user} UNKNOWN {cmd_key}")

                    time.sleep(POLL_INTERVAL)

        except Exception:
            logger.exception("RCON loop error, retrying in 5s")
            time.sleep(5)


if __name__ == "__main__":
    main()
