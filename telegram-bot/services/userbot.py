import os
import time
import asyncio
from telethon import TelegramClient, functions, types
from telethon.errors import FloodWaitError
import config

# ===============================
# SETUP SESSION
# ===============================
SESS_DIR = "sessions"
if not os.path.exists(SESS_DIR):
    os.makedirs(SESS_DIR)

client = TelegramClient(
    os.path.join(SESS_DIR, "admin_userbot"),
    config.API_ID,
    config.API_HASH,
    sequential_updates=True
)

_userbot_lock = asyncio.Lock()

# ===============================
# START USERBOT (DIPANGGIL SEKALI)
# ===============================
async def start_userbot(application):
    async with _userbot_lock:
        if not client.is_connected():
            await client.start()

            me = await client.get_me()
            application.bot_data["userbot"] = {
                "status": "CONNECTED",
                "since": time.strftime("%Y-%m-%d %H:%M:%S"),
                "dc": client.session.dc_id,
                "me": f"@{me.username}" if me.username else me.first_name
            }
            print("🤖 Userbot connected")
# ===============================
# GET REAL DC (FIX TOTAL)
# ===============================
async def get_real_dc(user_id):
    try:
        if not client.is_connected():
            raise RuntimeError("Userbot belum dijalankan")

        full_user = await asyncio.wait_for(
            client(functions.users.GetFullUserRequest(id=user_id)),
            timeout=8
        )

        if full_user.full_user.profile_photo:
            if isinstance(full_user.full_user.profile_photo, types.UserProfilePhoto):
                return full_user.full_user.profile_photo.dc_id

        return "Unknown/Hidden"

    except Exception as e:
        print(f"[Userbot DC Error] {e}")
        return "Unknown"

# ===============================
# GET FULL DETAILS (DIPAKAI /info)
# ===============================
async def get_full_details(user_id):
    try:
        if not client.is_connected():
            raise RuntimeError("Userbot belum dijalankan")

        result = await asyncio.wait_for(
            client(functions.users.GetFullUserRequest(id=user_id)),
            timeout=8
        )

        user = result.users[0]
        full = result.full_user

        return {
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
            "username": user.username or "-",
            "bio": full.about or "Tidak ada bio",
            "is_bot": user.bot,
            "is_verified": user.verified,
            "is_premium": user.premium,
            "is_scam": user.scam,
            "dc_id": await get_real_dc(user_id),
        }

    except asyncio.TimeoutError:
        print("[Userbot Full Details] Timeout")
        return None
    except Exception as e:
        print(f"[Userbot Full Details Error] {e}")
        return None
#=============== CEK INFO GRUP ===========
async def get_group_or_channel(target):
    try:
        if not client.is_connected():
            raise RuntimeError("Userbot belum dijalankan")

        if isinstance(target, str) and target.startswith("-100"):
            try:
                entity = await client.get_entity(int(target))
            except Exception:
                return None
        else:
            entity = await client.get_entity(target)


        if not isinstance(entity, (types.Chat, types.Channel)):
            return None

        full = await client(
            functions.channels.GetFullChannelRequest(entity)
        )

        return {
            "id": entity.id,
            "title": entity.title,
            "username": entity.username or "-",
            "type": "Group" if getattr(entity, "megagroup", False) else "Channel",
            "members": full.full_chat.participants_count,
            "verified": entity.verified,
            "scam": entity.scam,
            "description": full.full_chat.about or "Tidak ada deskripsi",
            "photo": entity.photo
        }

    except FloodWaitError as e:
        # ❗ JANGAN retry FloodWait besar
        print(f"[Group/Channel FloodWait] wait={e.seconds}s target={target}")
        return None

    except Exception as e:
        print(f"[Group/Channel Error] {e}")
        return None


async def get_channel_photo(username=None, entity=None):
    path = None
    try:
        if not client.is_connected():
            return None

        # ===============================
        # PRIORITAS 1: USERNAME PUBLIK
        # ===============================
        if username and username != "-":
            try:
                entity = await client.get_entity(f"https://t.me/{username}")
            except Exception:
                entity = None

        # ===============================
        # PRIORITAS 2: ENTITY (JIKA ADA)
        # ===============================
        if not entity:
            return None

        photos = await client.get_profile_photos(entity, limit=1)
        if not photos:
            return None

        path = await client.download_media(photos[0])
        if not path or not os.path.exists(path):
            return None

        return path

    except Exception as e:
        print(f"[Channel Photo Error] {e}")
        if path and os.path.exists(path):
            os.remove(path)
        return None

