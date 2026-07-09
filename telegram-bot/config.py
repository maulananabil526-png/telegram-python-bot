import os
from dotenv import load_dotenv

# Load dari .env file
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "owner")

# API untuk userbot
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
SESSION_DIR = "sessions"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN belum diset di ENV")
