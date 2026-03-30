import time
from datetime import datetime

COMMAND_FILE = "yt_commands.txt"
COUNTDOWN_FILE = "tnt_countdown.txt"
INTERVAL = 5 * 60  # 5 minutes in seconds

while True:
    # Countdown
    for remaining in range(INTERVAL, 0, -1):
        # Always write the value as a plain string without extra spaces
        with open(COUNTDOWN_FILE, "w", encoding="utf-8") as f:
            f.write(str(remaining))
        time.sleep(1)

    # Trigger TNT rain command
    with open(COMMAND_FILE, "a", encoding="utf-8") as f:
        f.write("!!tnt_rain\n")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] TNT rain triggered!")
