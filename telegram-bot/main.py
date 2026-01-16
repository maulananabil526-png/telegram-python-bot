import os
import pkgutil
import importlib
import threading
import time
import json
import asyncio
from datetime import date

from flask import Flask, request
from telegram.ext import ApplicationBuilder
from telegram.request import HTTPXRequest
from telegram import BotCommand

import config
from services.userbot import start_userbot

# =======================
# GLOBALS
# =======================
RUNTIME_FILE = "storage/runtime_stats.json"

telegram_app = None
main_loop = None

# =======================
# RUNTIME STATS
# =======================
def load_runtime_stats(application):
    if not os.path.exists(RUNTIME_FILE):
        return

    try:
        with open(RUNTIME_FILE, "r") as f:
            raw = f.read().strip()
            if not raw:
                return

        data = json.loads(raw)
        application.bot_data["users"] = data.get("users", {})

        cekbio = data.get("cekbio", {})
        today = date.today().isoformat()

        last_reset = cekbio.get("last_reset", today)
        daily_checked = cekbio.get("daily_checked", 0)

        if last_reset != today:
            daily_checked = 0
            last_reset = today

        application.bot_data["cekbio"] = {
            "total_checked": cekbio.get("total_checked", 0),
            "daily_checked": daily_checked,
            "last_reset": last_reset,
            "senders": cekbio.get("senders", [])
        }

        generate = data.get("generate", {})
        application.bot_data["generate"] = {
            "users": generate.get("users", []),
            "total_generated": generate.get("total_generated", 0)
        }

        print("💾 Runtime stats loaded")

    except Exception as e:
        print("❌ load_runtime_stats:", e)


def save_runtime_stats(application):
    try:
        if not application:
            return

        os.makedirs("storage", exist_ok=True)

        cekbio = application.bot_data.get("cekbio", {})
        generate = application.bot_data.get("generate", {})

        data = {
            "users": application.bot_data.get("users", {}),
            "cekbio": {
                "total_checked": cekbio.get("total_checked", 0),
                "daily_checked": cekbio.get("daily_checked", 0),
                "senders": cekbio.get("senders", [])
            },
            "generate": {
                "users": generate.get("users", []),
                "total_generated": generate.get("total_generated", 0)
            }
        }

        with open(RUNTIME_FILE, "w") as f:
            json.dump(data, f, indent=2)

    except Exception as e:
        print("❌ save_runtime_stats:", e)


def autosave_loop():
    while True:
        try:
            if telegram_app and telegram_app.bot_data:
                if (
                    telegram_app.bot_data.get("users")
                    or telegram_app.bot_data.get("cekbio", {}).get("senders")
                    or telegram_app.bot_data.get("generate", {}).get("users")
                ):
                    save_runtime_stats(telegram_app)
        except Exception as e:
            print("autosave:", e)

        time.sleep(60)

# =======================
# FLASK KEEP-ALIVE (RENDER)
# =======================
flask_app = Flask(__name__)

@flask_app.route("/", methods=["GET"])
def index():
    return {"status": "ok"}

@flask_app.route("/backend-heartbeat", methods=["POST"])
def backend_heartbeat():
    backend = telegram_app.bot_data.setdefault("backend", {})
    backend["status"] = "ON"
    backend["last_seen"] = time.time()
    backend["notified"] = False
    return {"ok": True}


def run_flask():
    port = int(os.getenv("PORT", 10000))
    flask_app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False
    )

# =======================
# BACKEND MONITOR
# =======================
def monitor_backend():
    while True:
        try:
            if not telegram_app:
                time.sleep(5)
                continue

            backend = telegram_app.bot_data.get("backend", {})
            last = backend.get("last_seen", 0)

            if last and time.time() - last > 30:
                if backend.get("status") != "OFF":
                    backend["status"] = "OFF"

                    if not backend.get("notified") and main_loop and not main_loop.is_closed():
                        asyncio.run_coroutine_threadsafe(
                            notify_backend_dead(last),
                            main_loop
                        )
                        backend["notified"] = True

        except Exception as e:
            print("monitor_backend:", e)

        time.sleep(15)


async def notify_backend_dead(last_seen):
    await telegram_app.bot.send_message(
        chat_id=config.OWNER_ID,
        text=(
            "⚠️ *BACKEND CEKBIO MATI*\n\n"
            f"⏰ Terakhir aktif: {time.strftime('%H:%M:%S', time.localtime(last_seen))}"
        ),
        parse_mode="Markdown"
    )

# =======================
# POST INIT
# =======================
async def post_init(application):
    global main_loop
    main_loop = asyncio.get_running_loop()

    load_runtime_stats(application)

    application.bot_data.setdefault("users", {})
    application.bot_data.setdefault("history", {})
    application.bot_data.setdefault("banned", [])
    application.bot_data.setdefault("premium_users", [])

    application.bot_data.setdefault("cekbio", {
        "total_checked": 0,
        "daily_checked": 0,
        "senders": []
    })

    application.bot_data.setdefault("generate", {
        "users": [],
        "total_generated": 0
    })

    application.bot_data.setdefault("backend", {
        "status": "UNKNOWN",
        "last_seen": 0,
        "notified": False
    })

    await start_userbot(application)
    print("✅ Userbot aktif")

    await application.bot.set_my_commands([
        BotCommand("start", "memulai bot"),
        BotCommand("pairing", "tambah sender"),
        BotCommand("cekbio", "cek bio"),
        BotCommand("generate", "acak email"),
        BotCommand("cekid", "id grup/chanel"),
        BotCommand("info", "reply teks/tag user"),
        BotCommand("cinfo", "info grup/chanel"),
        BotCommand("admin", "admin panel"),
    ])

# =======================
# LOAD HANDLERS
# =======================
def load_handlers(application):
    handlers_path = os.path.join(os.path.dirname(__file__), "handlers")

    for _, name, _ in pkgutil.iter_modules([handlers_path]):
        try:
            module = importlib.import_module(f"handlers.{name}")
            if hasattr(module, "setup"):
                module.setup(application)
                print(f"🧩 Handler loaded: {name}")
        except Exception as e:
            print(f"❌ Handler {name}:", e)

# =======================
# MAIN
# =======================
def main():
    request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=30,
        read_timeout=60,
        write_timeout=60
    )

    application = (
        ApplicationBuilder()
        .token(config.BOT_TOKEN)
        .request(request)
        .post_init(post_init)
        .build()
    )

    global telegram_app
    telegram_app = application

    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=monitor_backend, daemon=True).start()
    threading.Thread(target=autosave_loop, daemon=True).start()

    load_handlers(application)

    print("🤖 Bot berjalan...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
