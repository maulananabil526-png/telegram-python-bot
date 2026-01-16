import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# API untuk userbot (Hans, dll)
HANS_API_KEY = os.getenv("HANS_API_KEY")
HANS_API_URL = os.getenv("HANS_API_URL")
SESSION_DIR = "sessions"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN belum diset di ENV")
