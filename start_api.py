import subprocess
import sys

import config

if config.API_ID == 12345678 or config.API_HASH.startswith("PASTE_"):
    raise SystemExit("Edit config.py and set API_ID and API_HASH first.")

command = [
    "docker", "run", "--name", "telegram-bot-api", "--rm", "-it",
    "-p", "8081:8081",
    "-v", "telegram-bot-api-data:/var/lib/telegram-bot-api",
    "aiogram/telegram-bot-api:latest",
    f"--api-id={config.API_ID}",
    f"--api-hash={config.API_HASH}",
    "--local",
]
print("Starting local Telegram Bot API server...")
print("Keep this window open while the bot is running.")
try:
    raise SystemExit(subprocess.call(command))
except FileNotFoundError:
    raise SystemExit("Docker was not found. Install and start Docker Desktop first.")
