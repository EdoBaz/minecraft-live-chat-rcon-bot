#!/usr/bin/env python3
"""
mc_rcon_control.py
Keeps viewer !tnt (single TNT) and adds system command !!tnt_rain (TNT rain with countdown).
Cross-platform file locking (filelock).
"""

import time
import logging
import datetime
import os
import sys
from pathlib import Path
from filelock import FileLock
from mcrcon import MCRcon

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from env_loader import get_float_env, get_int_env, get_required_env, load_env_file

load_env_file(PROJECT_ROOT / ".env")

# ---------------- CONFIG ----------------
RCON_HOST       = os.getenv("RCON_HOST", "localhost")
RCON_PORT       = get_int_env("RCON_PORT", 25575)
RCON_PASSWORD   = get_required_env("RCON_PASSWORD")
PLAYER          = os.getenv("PLAYER", "Player")
POLL_INTERVAL   = get_float_env("POLL_INTERVAL", 5.0)

# Rate limit: how many commands to process per cycle
COMMAND_LIMIT    = get_int_env("COMMAND_LIMIT", 3)

# thresholds follower -> pickaxe (example values)
THRESHOLDS = [
    (5125, "netherite"),
    (2625, "diamond"),
    (1625, "golden"),
    (625,  "iron"),
    (225,  "stone"),
    (125,  "wooden"),
]

# Files
FILE_FOLLOWERS    = Path(os.getenv("FILE_FOLLOWERS", "yt_follower_count.txt"))
FILE_EFF_LEVEL    = Path(os.getenv("FILE_EFF_LEVEL", "eff_level.txt"))
FILE_CURRENT_PICK = Path(os.getenv("FILE_CURRENT_PICK", "current_pickaxe.txt"))
POLL_FILE         = Path(os.getenv("POLL_FILE", "yt_commands.txt"))
HISTORY_FILE      = Path(os.getenv("PROCESSED_HISTORY", "processed_commands.log"))

# Countdown file that OBS will read (Text source: Read from file)
TNT_COUNTDOWN_FILE = Path(os.getenv("TNT_COUNTDOWN_FILE", "tnt_countdown.txt"))

# Normal mappings for viewer commands (leave !tnt as-is for viewers)
MAPPINGS = {
    "!boost":   f"effect give {PLAYER} haste 10 2",
    "!slow":    f"effect give {PLAYER} slowness 10 1",
    "!speed":   f"effect give {PLAYER} speed 10 1",
    "!water":   f"execute as {PLAYER} at {PLAYER} run setblock ~ ~-1 ~ water",
    "!milk":    f"effect clear {PLAYER}",
    "!fatigue": f"effect give {PLAYER} mining_fatigue 10 1",
    # "!tnt": left out on purpose from MAPPINGS to handle both viewer single-tnt and
    # system TNT rain separately below. However, if you want viewers' !tnt to use
    # the simple summon, you can either keep it here or handle explicitly.
}

# Use this literal as viewer single TNT, we'll handle it in code (keeps parity with previous)
VIEWER_TNT_CMD = "!tnt"

# System command token (must be appended by your system/admin scripts)
SYSTEM_TNT_RAIN_CMD = "!!tnt_rain"

# Cleanup command for items (unchanged)
CLEANUP_INTERVAL_MINUTES = get_int_env("CLEANUP_INTERVAL_MINUTES", 15)
CLEANUP_COMMAND = '/kill @e[type=minecraft:item,nbt={Item:{id:"minecraft:cobblestone"}}]'

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("mc_rcon_control")

# -----------------------------------------


def read_int_file(path: Path, default=0):
    try:
        return int(path.read_text().strip())
    except Exception:
        return default


def write_int_file(path: Path, val):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(int(val)))
    except Exception as e:
        logger.exception("write_int_file error: %s", e)


def read_str_file(path: Path, default=""):
    try:
        return path.read_text().strip()
    except Exception:
        return default


def write_str_file(path: Path, s: str):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(s)
    except Exception as e:
        logger.exception("write_str_file error: %s", e)


def append_history(line: str):
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        lock = FileLock(str(HISTORY_FILE) + ".lock")
        with lock:
            with HISTORY_FILE.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())
    except Exception:
        logger.exception("append_history error")


# ---------------- file queue helpers (locked) ----------------
def read_queue_and_clear(path: Path):
    """Read lines from POLL_FILE and then truncate it atomically with a FileLock.
       Returns list of stripped lines (order preserved)."""
    items = []
    lock = FileLock(str(path) + ".lock")
    with lock:
        if not path.exists():
            return items
        with path.open("r+", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    items.append(ln)
            # truncate
            f.seek(0)
            f.truncate()
    return items


def write_queue_atomic(path: Path, items):
    """Overwrite queue file with items (list of strings) atomically using FileLock."""
    lock = FileLock(str(path) + ".lock")
    with lock:
        with path.open("w", encoding="utf-8") as f:
            for it in items:
                f.write(str(it).strip() + "\n")
            f.flush()
            os.fsync(f.fileno())


# ---------------- TNT countdown (OBS) helpers ----------------
def write_countdown_text(text: str):
    try:
        TNT_COUNTDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TNT_COUNTDOWN_FILE.write_text(str(text), encoding="utf-8")
    except Exception:
        logger.exception("write_countdown_text failed")


def clear_countdown_text():
    try:
        TNT_COUNTDOWN_FILE.write_text("", encoding="utf-8")
    except Exception:
        pass


# ---------------- pickaxe helper ----------------
def pickaxe_for_followers(count: int) -> str:
    for thr, mat in THRESHOLDS:
        if count >= thr:
            return mat
    return THRESHOLDS[-1][1]


# ---------------- RCON helper ----------------
def send_rcon(cmd: str, rcon: MCRcon):
    try:
        resp = rcon.command(cmd)
        logger.info("> %s\n< %s", cmd, resp)
    except Exception:
        logger.exception("send_rcon failed for: %s", cmd)


# ---------------- TNT RAIN sequence (system command) ----------------
def perform_tnt_rain(rcon: MCRcon, player: str, countdown_seconds=6, tnt_count=36, radius=5, protect_seconds=10):
    """
    Perform TNT rain:
      - give high resistance to player for protect_seconds
      - write countdown to TNT_COUNTDOWN_FILE so OBS can show it
      - spawn tnt_count primed TNTs around the player within radius
      - clear countdown file
    """
    try:
        logger.info("Starting TNT RAIN: countdown %ss, tnt_count=%d, radius=%d", countdown_seconds, tnt_count, radius)
        # 1) Give strong resistance (level 10) to player for protect_seconds
        #    hideParticles true -> 'true' at the end may be supported by your server version.
        send_rcon(f"effect give {player} resistance {protect_seconds} 10 true", rcon)

        # 2) Countdown (write to file each second)
        for s in range(countdown_seconds, 0, -1):
            write_countdown_text(f"⚠ TNT in: {s}s")
            time.sleep(1)

        write_countdown_text("💥 BOOM!")
        time.sleep(0.2)

        # 3) Spawn TNTs around player: use small fuse for fast explosion
        spawned = 0
        offsets = []
        for dx in range(-radius, radius + 1):
            for dz in range(-radius, radius + 1):
                if dx == 0 and dz == 0:
                    continue
                offsets.append((dx, dz))

        # optionally shuffle for nicer distribution
        # random.shuffle(offsets)

        for dx, dz in offsets:
            if spawned >= tnt_count:
                break
            # small fuse for immediate boom
            nbt = "{Fuse:1}"
            cmd = f"execute as {player} at {player} run summon tnt ~{dx} ~1 ~{dz} {nbt}"
            send_rcon(cmd, rcon)
            spawned += 1
            # tiny spacing to smooth the spawn (feel free to adjust)
            time.sleep(0.04)

        # 4) small wait so explosions happen, then clear countdown file
        time.sleep(0.5)
        clear_countdown_text()
        logger.info("TNT RAIN finished: spawned %d tnts", spawned)

    except Exception:
        logger.exception("perform_tnt_rain error")
        try:
            clear_countdown_text()
        except:
            pass


# ---------------- MAIN ----------------
def ensure_files_exist():
    if not FILE_CURRENT_PICK.exists():
        FILE_CURRENT_PICK.write_text(pickaxe_for_followers(0), encoding="utf-8")
    if not FILE_FOLLOWERS.exists():
        FILE_FOLLOWERS.write_text("0", encoding="utf-8")
    if not FILE_EFF_LEVEL.exists():
        FILE_EFF_LEVEL.write_text("0", encoding="utf-8")
    # ensure countdown file present (empty)
    try:
        TNT_COUNTDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not TNT_COUNTDOWN_FILE.exists():
            TNT_COUNTDOWN_FILE.write_text("", encoding="utf-8")
    except Exception:
        pass


def main():
    ensure_files_exist()
    logger.info("🚀 Starting mc_rcon_control.py (with TNT rain capability)")
    last_cleanup_time = datetime.datetime.utcnow()

    # connect to RCON and loop
    while True:
        try:
            with MCRcon(RCON_HOST, RCON_PASSWORD, port=RCON_PORT) as mcr:
                logger.info("✅ Connected to RCON at %s:%s", RCON_HOST, RCON_PORT)

                while True:
                    # read basic state (tolerant to read errors)
                    try:
                        followers = read_int_file(FILE_FOLLOWERS, default=0)
                    except Exception:
                        followers = 0
                    current_mat = read_str_file(FILE_CURRENT_PICK, default=pickaxe_for_followers(0))
                    try:
                        eff_level = read_int_file(FILE_EFF_LEVEL, default=0)
                    except Exception:
                        eff_level = 0

                    # periodic cleanup of dropped items
                    now = datetime.datetime.utcnow()
                    if (now - last_cleanup_time).total_seconds() >= CLEANUP_INTERVAL_MINUTES * 60:
                        logger.info("Cleaning ground drops")
                        send_rcon(CLEANUP_COMMAND, mcr)
                        last_cleanup_time = now

                    # change pickaxe if follower thresholds cross
                    new_mat = pickaxe_for_followers(followers)
                    if new_mat != current_mat:
                        logger.info("%d followers -> switching to %s pickaxe", followers, new_mat)
                        send_rcon(f"item replace entity {PLAYER} weapon.mainhand with air", mcr)
                        nbt0 = '{Unbreakable:1b,Enchantments:[{id:"minecraft:efficiency",lvl:0s}]}'
                        send_rcon(f"item replace entity {PLAYER} weapon.mainhand with minecraft:{new_mat}_pickaxe{nbt0}", mcr)
                        current_mat = new_mat
                        eff_level = 0
                        write_str_file(FILE_CURRENT_PICK, current_mat)
                        write_int_file(FILE_EFF_LEVEL, eff_level)

                    # increase efficiency gradually based on follower offset
                    base_thr = 0
                    for thr, _ in THRESHOLDS:
                        if followers >= thr:
                            base_thr = thr
                            break
                    target_eff = max(0, followers - base_thr)
                    if eff_level < target_eff:
                        eff_level += 1
                        logger.info("Setting efficiency level %d", eff_level)
                        nbt_eff = '{Unbreakable:1b,Enchantments:[{id:"minecraft:efficiency",lvl:' + str(eff_level) + '}]}'
                        send_rcon(f"item replace entity {PLAYER} weapon.mainhand with minecraft:{current_mat}_pickaxe{nbt_eff}", mcr)
                        write_int_file(FILE_EFF_LEVEL, eff_level)

                    # ---------- COMMANDS QUEUE PROCESS ----------
                    queue = read_queue_and_clear(POLL_FILE)
                    if queue:
                        logger.info("Found %d queued commands", len(queue))

                    # take up to COMMAND_LIMIT, put remainder back
                    to_process = queue[:COMMAND_LIMIT]
                    remaining = queue[COMMAND_LIMIT:]
                    if remaining:
                        write_queue_atomic(POLL_FILE, remaining)

                    # process commands_to_process in order
                    for raw_cmd in to_process:
                        cmd = raw_cmd.strip()
                        if not cmd:
                            continue

                        # System TNT rain token (special)
                        if cmd == SYSTEM_TNT_RAIN_CMD:
                            logger.info("SYSTEM command detected: TNT RAIN")
                            # we treat this as system-level: immediate execution
                            perform_tnt_rain(mcr, PLAYER, countdown_seconds=6, tnt_count=36, radius=5, protect_seconds=10)
                            append_history(f"{datetime.datetime.utcnow().isoformat()}Z SYSTEM {cmd}")
                            continue

                        # Viewer single TNT: keep this behavior (spawns 1 primed tnt at player)
                        if cmd == VIEWER_TNT_CMD:
                            # spawn a single primed tnt with small fuse under the player
                            logger.info("Viewer !tnt detected: spawn single TNT")
                            nbt = "{Fuse:1}"
                            send_rcon(f"execute as {PLAYER} at {PLAYER} run summon tnt ~ ~-1 ~ {nbt}", mcr)
                            append_history(f"{datetime.datetime.utcnow().isoformat()}Z VIEWER {cmd}")
                            continue

                        # Other mapped viewer commands
                        if cmd in MAPPINGS:
                            mapped = MAPPINGS[cmd]
                            logger.info("Mapped command: %s -> %s", cmd, mapped)
                            send_rcon(mapped, mcr)
                            append_history(f"{datetime.datetime.utcnow().isoformat()}Z VIEWER {cmd}")
                            # special-case water: remove water after some seconds (like your previous logic)
                            if cmd == "!water":
                                time.sleep(10)
                                send_rcon(f"execute as {PLAYER} at {PLAYER} run setblock ~ ~-1 ~ air", mcr)
                            continue

                        # Unknown command: log
                        logger.info("Unknown/unhandled command in queue: %s", cmd)
                        append_history(f"{datetime.datetime.utcnow().isoformat()}Z UNKNOWN {cmd}")

                    # end commands processing
                    time.sleep(POLL_INTERVAL)

        except Exception:
            logger.exception("RCON main loop exception - retrying in 5s")
            time.sleep(5)


if __name__ == "__main__":
    main()
