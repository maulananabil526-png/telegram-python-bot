import os
import pkgutil
import importlib
import threading
import time
import json
import asyncio
from flask import Flask, request
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler
)
from telegram.request import HTTPXRequest
from telegram import BotCommand
from services.userbot import start_userbot
import config
from config import BOT_TOKEN
from datetime import date

RUNTIME_FILE = "storage/runtime_stats.json"
telegram_app = None
main_loop = None

# =======================
# RUNTIME STATS
# =======================
def load_runtime_stats(application):
    if not os.path.exists(RUNTIME_FILE):
        print("ℹ️ runtime_stats.json belum ada")
        return

    try:
        with open(RUNTIME_FILE, "r") as f:
            raw = f.read().strip()

        if not raw:
            print("⚠️ runtime_stats.json kosong, di-skip")
            return

        data = json.loads(raw)
        application.bot_data["users"] = data.get("users", {})

        cekbio = data.get("cekbio", {})
        today = date.today().isoformat()

        last_reset = cekbio.get("last_reset", today)

        daily_checked = cekbio.get("daily_checked", 0)

        # ✅ RESET JIKA HARI BERGANTI
        if last_reset != today:
            daily_checked = 0
            last_reset = today

        application.bot_data["cekbio"] = {
            "total_checked": cekbio.get("total_checked", 0),
            "daily_checked": daily_checked,
            "last_reset": last_reset,          # ✅ BARU
            "senders": cekbio.get("senders", [])
        }

        generate = data.get("generate", {})

        application.bot_data["generate"] = {
            "users": generate.get("users", []),
            "total_generated": generate.get("total_generated", 0)
        }

        print("💾 Runtime stats loaded")

    except Exception as e:
        print("❌ load_runtime_stats error:", e)

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
        print("❌ save_runtime_stats error:", e)

def autosave_loop():
    while True:
        try:
            if not telegram_app or not telegram_app.bot_data:
                time.sleep(5)
                continue

            # 🔑 SAVE JIKA SALAH SATU ADA ISI
            if (
                telegram_app.bot_data.get("users")
                or telegram_app.bot_data.get("cekbio", {}).get("senders")
                or telegram_app.bot_data.get("generate", {}).get("users")
            ):
                save_runtime_stats(telegram_app)

        except Exception as e:
            print("autosave error:", e)

        time.sleep(60)

# =======================
# BACKEND MONITOR
# =======================

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
        BotCommand("cinfo","info grup/chanel"),
        BotCommand("admin","admin panel")
    ])

# =======================
# LOAD HANDLERS
# =======================
def load_handlers(application):
    handlers_path = os.path.join(os.path.dirname(__file__), "handlers")

    print("🔍 Memuat handlers...")

    for _, name, _ in pkgutil.iter_modules([handlers_path]):
        try:
            module = importlib.import_module(f"handlers.{name}")

            if hasattr(module, "setup"):
                module.setup(application)
                print(f"🧩 Handlers dimuat: {name}")
            else:
                print(f"⚠️ Handlers dilewati (tanpa setup): {name}")

        except Exception as e:
            print(f"❌ Gagal memuat handler {name}: {e}")

    print("🔥 Semua handler selesai dimuat")
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
        .token(BOT_TOKEN)
        .request(request)
        .post_init(post_init)
        .build()
    )

    global telegram_app
    telegram_app = application

    #threading.Thread(
    #    target=flask_app.run,
    #    kwargs={"host": "127.0.0.1", "port": 5000, "debug": False, "use_reloader": False},
    #    daemon=True
    #).start()

    #threading.Thread(target=monitor_backend, daemon=True).start()
    threading.Thread(target=autosave_loop, daemon=True).start()

    load_handlers(application)

    print("🤖 Bot berjalan...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

