import os
import re
import time
import asyncio
from datetime import datetime, date

import aiohttp
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters
)
from handlers.admin import maintenance_guard, track_user
from services.session import is_paired, get_user_mode
from keyboards.owner import kb_owner

NODE_URL = "http://127.0.0.1:3000/cekbio"
SEND_AS_FILE = True
MAX_FILE_NUMBERS = 5000
MAX_NUMBERS = 500

MODE_CONFIG = {
    "Slow": {
        "batch": 10,
        "delay": 2.0
    },
    "Medium": {
        "batch": 25,
        "delay": 1.0
    },
    "Fast": {
        "batch": 50,
        "delay": 0.5
    }
}

ACTIVE_JOBS = {}
CANCEL_FLAGS = {}

# =========================
# UTIL
# =========================

def chunk_list(data, size):
    for i in range(0, len(data), size):
        yield data[i:i + size]


def parse_numbers(text: str):
    nums = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            nums.append(line)
    return nums


def fmt_time(ts):
    if not ts or ts == 0:
        return "Tidak diketahui"
    try:
        if ts > 10**12:  # milliseconds
            ts = ts / 1000
        return datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return "Gagal memproses waktu"


def progress_bar(done, total, length=14):
    if total == 0:
        return "[░░░░░░░░░░░░░░] 0%"
    filled = int(length * done / total)
    percent = int((done / total) * 100)
    return "[" + "█" * filled + "░" * (length - filled) + f"] {percent}%"

def cancel_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_cekbio")]
    ])
# =========================
# COMMAND
# =========================
async def parse_numbers_from_file(message):
    doc = message.document
    if not doc:
        return []

    if not doc.file_name.lower().endswith((".txt", ".csv")):
        return []

    file = await doc.get_file()
    data = await file.download_as_bytearray()

    text = data.decode("utf-8", errors="ignore")

    numbers = []
    for line in text.splitlines():
        # ambil hanya angka
        digits = re.sub(r"\D", "", line)

        if len(digits) >= 8:
            numbers.append(digits)

    return list(dict.fromkeys(numbers))  # remove duplicate

async def cekbio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await maintenance_guard(update, context):
        return
    track_user(update, context, "cekbio")
    user_id = update.effective_user.id

    cekbio_data = context.application.bot_data.setdefault("cekbio", {
        "total_checked": 0,
        "daily_checked": 0,
        "last_reset": date.today().isoformat(),  # ⬅️ BARU
        "senders": []
    })

    today = date.today().isoformat()
    if cekbio_data.get("last_reset") != today:
        cekbio_data["daily_checked"] = 0
        cekbio_data["last_reset"] = today

    senders = cekbio_data["senders"]

    if user_id not in senders:
        senders.append(user_id)

    if not is_paired(user_id):
        await update.message.reply_text(
            "❌ *belum ada sender aktif*\n"
            "  _Silahkan /pairing dulu._",
            reply_markup=kb_owner(),
            parse_mode="Markdown"
        )
        return

    if ACTIVE_JOBS.get(user_id):
        await update.message.reply_text(
            "⏳ Proses masih berjalan."
        )
        return

    numbers = []
    is_file = False

    # ===== MODE FILE =====
    if update.message.document:
        is_file = True
        numbers = await parse_numbers_from_file(update.message)

        if not numbers:
            await update.message.reply_text(
                "❌ File tidak valid.\nGunakan .txt atau .csv berisi nomor."
            )
            return

    # ===== MODE TEXT =====
    else:
        text = update.message.text.replace("/cekbio", "").strip()
        numbers = parse_numbers(text)

    if not numbers:
        await update.message.reply_text(
            f"   ❌*tidak ada nomor valid*\n\n"
            f" _contoh : /cekbio 584163007274_\n\n"
            f" atau reply file yang berisi nomor\n"
            f" •upload file berupa .txt atau .csv\n"
            f" •maksimal {MAX_FILE_NUMBERS} untuk file",
            parse_mode="Markdown"
        )
        return

    if len(numbers) > MAX_NUMBERS:
        await update.message.reply_text(
            f"❌ Maksimal {MAX_NUMBERS} nomor untuk cekbio."
        )
    if len(numbers) > MAX_FILE_NUMBERS:
        await update.message.reply_text(
            f"❌ Maksimal {MAX_FILE_NUMBERS} nomor per file."
        )
        return


    ACTIVE_JOBS[user_id] = True
    CANCEL_FLAGS[user_id] = False
    context.user_data["numbers"] = numbers
    context.user_data["input_type"] = "file" if is_file else "text"

    if is_file:
        msg_text = (
            "📂 File diterima\n"
            f"📊 Total nomor: {len(numbers)}\n\n"
            "[░░░░░░░░░░░░░░] 0%\n"
            "⏳ Menyiapkan pengecekan..."
        )
    else:
        msg_text = (
            "⏳ Memulai pengecekan nomor\n"
            f"📊 Total: {len(numbers)} nomor\n\n"
            "[░░░░░░░░░░░░░░] 0%\n"
            "🔍 Menghubungkan ke WhatsApp..."
        )

    msg = await update.message.reply_text(
        msg_text,
        reply_markup=cancel_keyboard()
    )

    context.user_data["progress_msg"] = msg

    context.application.create_task(
        cekbio_process(update, context)
    )


async def cancel_cekbio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    CANCEL_FLAGS[user_id] = True
    await update.callback_query.answer("Proses akan dihentikan...")


# =========================
# PROCESS
# =========================

async def cekbio_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    start_time = time.time()

    mode = get_user_mode(user_id)
    conf = MODE_CONFIG.get(mode, MODE_CONFIG["Medium"])

    batch_size = conf["batch"]
    delay = conf["delay"]

    numbers = context.user_data["numbers"]
    total = len(numbers)
    processed = 0

    # hasil mentah dari node
    registered = []
    not_registered = []

    progress_msg = context.user_data.get("progress_msg")

    async def check_cancel():
        if CANCEL_FLAGS.get(user_id):
            raise asyncio.CancelledError

    try:
        timeout = aiohttp.ClientTimeout(total=300)
        async with aiohttp.ClientSession(timeout=timeout) as session:

            for batch in chunk_list(numbers, batch_size):

                # ===== CANCEL CHECK (BOUNDARY BATCH) =====
                await check_cancel()

                payload = {
                    "userId": user_id,
                    "numbers": batch,
                    "mode": mode
                }

                async with session.post(NODE_URL, json=payload) as resp:
                    data = await resp.json()

                for item in data.get("results", []):
                    await check_cancel()
                    if not item.get("registered"):
                        not_registered.append(item["number"])
                    else:
                        registered.append(item)

                processed += len(batch)

                # ===== PROGRESS BAR =====
                if progress_msg:
                    bar = progress_bar(processed, total)
                    await progress_msg.edit_text(
                        "⏳ Cekbio sedang diproses\n\n"
                        f"{bar}\n"
                        f"📊 {processed}/{total} nomor\n"
                        f"⚡ Mode: {mode}",
                        reply_markup=cancel_keyboard()
                    )

                await asyncio.sleep(delay)

        # =========================
        # PROSES OUTPUT (GROUPING)
        # =========================

        # hapus pesan progress biar rapi
        if progress_msg:
            try:
                await progress_msg.delete()
            except Exception:
                pass

        with_bio = []
        registered_only = []
        not_registered = not_registered

        for r in registered:
            bio = r.get("bio", "")
            has_bio = bool(bio and bio.strip() and bio.strip() != "-")
            if has_bio:
               with_bio.append(r)
            else:
               registered_only.append(r)

        business_count = sum(
           1 for r in registered if r.get("type") == "Business"
        )

        duration = int(time.time() - start_time)

        # =========================
        # BUILD OUTPUT TEXT
        # =========================

        text = (
            "📋  HASIL CEKBIO \n"
            f" Tanggal : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
            "=================================\n"
            f"📊 Total Dicek : {total}\n"
            f"🟢 Ada Bio     : {len(with_bio)}\n"
            f"🟡 Terdaftar   : {len(registered_only) + len (with_bio)}\n"
            f"🔴 Tidak Ada   : {len(not_registered)}\n"
            f"🏢 Busines     : {business_count}\n"
            f"⏱️  Durasi     : {duration} detik\n"
            f"⚡ Mode        : {mode}\n\n"
        )

        def render_section(title, items):
            if not items:
                return ""
            out = f"{title}\n"
            for i, r in enumerate(items, 1):
                out += (
                    f"{i}) {r['number']}\n"
                    f"   • Bio : {r.get('bio','-')}\n"
                    f"   • Set : {fmt_time(r.get('updated'))}\n"
                )
            return out + "\n"

        if with_bio:
            text += "🟢 ADA BIO (PERSONAL & BUSINESS)\n"
            for i, r in enumerate(with_bio, 1):
                label = " [•BUSINESS•]" if r.get("type") == "Business" else ""
                text += (
                    f"{i}) {r['number']}{label}\n"
                    f"   • Bio : {r.get('bio','-')}\n"
                    f"   • Set : {fmt_time(r.get('updated'))}\n"
                )
            text += "\n"

        if registered_only:
            text += "🟡 TERDAFTAR (Tanpa Bio)\n"
            for i, r in enumerate(registered_only, 1):
                label = " [•Business•]" if r.get("type") == "Business" else ""
                text += f"{i}) {r['number']}{label}\n"
            text += "\n"

        if not_registered:
            text += "🔴 TIDAK TERDAFTAR\n"
            for i, n in enumerate(not_registered, 1):
                text += f"{i}) {n}\n"

        # =========================
        # SEND OUTPUT (1x)
        # =========================
        total = len(numbers)
        cekbio_data = context.application.bot_data.setdefault("cekbio", {
            "total_checked": 0,
            "daily_checked": 0,
            "last_reset": date.today().isoformat(),
            "senders": []
        })

        today = date.today().isoformat()
        if cekbio_data.get("last_reset") != today:
            cekbio_data["daily_checked"] = 0
            cekbio_data["last_reset"] = today

        cekbio_data["total_checked"] += total
        cekbio_data["daily_checked"] += total

        if SEND_AS_FILE:
            filename = f"cekbio_{user_id}.txt"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(text)

            await update.message.reply_document(
                document=open(filename, "rb"),
                filename="cekbio.txt",
                caption=(
                     "📋⧼ HASIL CEKBIO ⧽\n"
                     f"━━━━━━━━━━━━━━\n"
                     f"📊 Total Dicek : {total}\n"
                     f"├─ Terdaftar: {len(registered_only) + len (with_bio)}\n"
                     f"├─ Tidak ada: {len(not_registered)}\n"
                     f"├─ Ada bio  : {len(with_bio)}\n"
                     f"└─ Busines  :  {business_count}\n"
                     f"⚡ Mode: {mode}"
                )
            )
            os.remove(filename)

    except asyncio.CancelledError:
        elapsed = int(time.time() - start_time)
        if progress_msg:
            await progress_msg.edit_text(
                "❌ Proses dibatalkan\n\n"
                f"📊 Diproses: {processed}/{total}\n"
                f"⏱️ Durasi: {elapsed} detik"
            )

        else:
            await update.message.reply_text(text, parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(
           f"❌ `Terjadi error`:\n`{e}`",
           reply_markup=kb_owner(),
           parse_mode="Markdown"
        )

    finally:
        ACTIVE_JOBS.pop(user_id, None)
        CANCEL_FLAGS.pop(user_id, None)
        context.user_data.clear()


# =========================
# SETUP
# =========================

def setup(app):
    app.add_handler(CommandHandler("cekbio", cekbio))
    app.add_handler(
        CallbackQueryHandler(cancel_cekbio, pattern="cancel_cekbio")
    )
    app.add_handler(
        MessageHandler(
            filters.Document.ALL & filters.CaptionRegex("^/cekbio"),
            cekbio
        )
    )

