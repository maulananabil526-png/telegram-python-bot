import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# API untuk userbot (Hans, dll)
API_ID = os.getenv("API_ID")
API_HANS = os.getenv("API_HANS")
SESSION_DIR = "sessions"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN belum diset di ENV")
