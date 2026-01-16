import requests
import time
import uuid
import asyncio
from handlers.admin import maintenance_guard
from keyboards.owner import kb_owner
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

from services.session import (
    USER_STATES,
    PAIRING_ACTIVE,
    PAIRING_TOKEN,
    LAST_PAIR_MSG,
    set_paired,
    clear_session,
    get_user_mode,
    save_user_mode,
    load_sessions
)

WA_API = "http://127.0.0.1:3000"

# ================= HELPER =================
def get_uptime(start_time):
    if not start_time:
        return "-"
    # Menghitung selisih waktu dalam detik
    delta = int(time.time() - (start_time / 1000))
    h, r = divmod(delta, 3600)
    m, s = divmod(r, 60)
    return f"{h}j {m}m {s}s"

def get_wa_status(user_id):
    try:
        r = requests.get(f"{WA_API}/status", params={"userId": user_id}, timeout=5).json()
        return r
    except:
        return {"ok": False, "status": "offline"}

# ================= DASHBOARD =================
async def show_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    res = get_wa_status(user_id)
    local_data = load_sessions().get(str(user_id), {})

    wa_number = res.get("number")
    if not wa_number:
        wa_number = local_data.get("wa_number", "—")

    online = bool(res.get("online"))
    paired = bool(res.get("paired"))

    if paired and online:
        current_mode = get_user_mode(user_id)
        text = (
            "╭━━━〔 🟢 **SESSION ACTIVE** 〕━━━\n"
            f"┃ 📱 **Nomor:** `{wa_number}`\n"
            f"┃ ⚡ **Mode:** `{current_mode}`\n"
            f"┃ ⏱️ **Uptime:** `{get_uptime(res.get('startTime'))}`\n"
            "┃ 📡 **Status:** `Online`\n"
            "╰━━━━━━━━━━━━━━━━━━━━"
        )
        kb = [
            [
               InlineKeyboardButton("🔴 Disconnect", callback_data="wa_disconnect"),
               InlineKeyboardButton("🔄 Change", callback_data="wa_change")
            ],
            [InlineKeyboardButton("⚙️ Set Mode Pengecekan", callback_data="wa_set_mode")]
        ]

    elif paired and not online:
        text = (
            "╭━━━〔 🟡 **RECONNECTING** 〕━━━\n"
            f"┃ 📱 **Nomor:** `{wa_number}`\n"
            "┃ 📡 **Status:** `Offline`\n"
            "╰━━━━━━━━━━━━━━━━━━━━\n\n"
            "Sesi ditemukan. Bot sedang mencoba menghubungkan ulang ke WhatsApp."
        )
        kb = [[
            InlineKeyboardButton("🔄 Refresh Status", callback_data="wa_refresh"),
            InlineKeyboardButton("🔴 Force Logout", callback_data="wa_disconnect")
        ]]

    else:
        text = (
            "╭━━〔 🔴 **NOT CONNECTED** 〕━━\n"
            "┃ 📱 **Nomor:** `—`\n"
            "┃ 📡 **Status:** `Disconnected`\n"
            "╰━━━━━━━━━━━━━━━━━\n"
            "Silakan hubungkan WhatsApp Anda."
        )
        kb = [[InlineKeyboardButton("🔗 Connect", callback_data="wa_connect")]]

    reply_markup = InlineKeyboardMarkup(kb)

    # 5️⃣ Kirim / edit pesan
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    else:
        await update.effective_chat.send_message(
            text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

#================= MODE MENU =================
async def show_mode_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    m = get_user_mode(user_id)

    text = (
        "⚙️ **PENGATURAN KECEPATAN**\n\n"
        "_Pilih mode sesuai kebutuhan_:\n"
        "• **Slow**: 12-15 dtk (Paling Aman)\n"
        "• **Medium**: 5-7 dtk (Standar)\n"
        "• **Fast**: 1-2 dtk (Cepat/Beresiko)\n\n"
        f"Mode saat ini: **{m}**"
    )

    kb = [
        [
            InlineKeyboardButton(f"{'✅ ' if m=='Slow' else ''}Slow", callback_data="wa_speed_Slow"),
            InlineKeyboardButton(f"{'✅ ' if m=='Medium' else ''}Medium", callback_data="wa_speed_Medium"),
            InlineKeyboardButton(f"{'✅ ' if m=='Fast' else ''}Fast", callback_data="wa_speed_Fast")
        ],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="wa_refresh")]
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
# ================= COMMAND =================
async def pairing_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await maintenance_guard(update, context):
        return

    user_id = update.effective_user.id

    # ✅ Kalau pairing masih aktif
    if PAIRING_ACTIVE.get(user_id):
        await update.message.reply_text(
            "⏳ _Pairing masih berlangsung_.\n"
            "silakan tunggu atau tekan *Cancel*.",
            parse_mode="Markdown"
        )
        return

    await show_dashboard(update, context)
# ================= CALLBACK HANDLER =================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await maintenance_guard(update, context):
        return

    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    await query.answer()

  #========= CONNECT ========
    if data == "wa_connect":
        USER_STATES[user_id] = "WAITING_NUMBER"
        await query.edit_message_text(
            "📩 Kirim **Nomor WhatsApp** kamu.\n\n"
            " Contoh: `584263890929`",
            parse_mode="Markdown"
        )
  #========= REFRESH =========
    elif data == "wa_refresh":
        await show_dashboard(update, context)

  #========= MODE ============
    elif data == "wa_set_mode":
        await show_mode_menu(update, context)

    elif data.startswith("wa_speed_"):
        mode_baru = data.replace("wa_speed_", "")
        save_user_mode(user_id, mode_baru)

        await query.answer(f"✅ Mode diubah ke {mode_baru}")
        await show_mode_menu(update, context) # Refresh menu mode

  #======== DISCONNECT ========
    elif data == "wa_disconnect":
        try:
            requests.get(f"{WA_API}/logout", params={"userId": user_id}, timeout=5)
        except:
            pass

        clear_session(user_id)
        USER_STATES.pop(user_id, None)
        PAIRING_ACTIVE.pop(user_id, None)

        await show_dashboard(update, context)

  #========= CHANGE ==========
    elif data == "wa_change":
        context.user_data["change_sender"] = True
        USER_STATES[user_id] = "WAITING_NUMBER"
        kb = [[InlineKeyboardButton("❌ Batal", callback_data="wa_cancel_change")]]

        await query.edit_message_text(
            "🔄 Session lama dihapus.\n"
            "Silakan kirim **Nomor WhatsApp baru** kamu:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )
# ========== CQNCEL CHANGE ========
    elif data == "wa_cancel_change":
        context.user_data.pop("change_sender", None)
        USER_STATES.pop(user_id, None)
        PAIRING_ACTIVE.pop(user_id, None)

        await show_dashboard(update, context)

  #========== CQNCELL ===========
    elif data == "wa_cancel_pairing":
        try:
            requests.get(
                f"{WA_API}/logout",
                params={"userId": user_id},
                timeout=5
           )
        except:
            pass

        PAIRING_ACTIVE.pop(user_id, None)
        PAIRING_TOKEN.pop(user_id, None)
        USER_STATES.pop(user_id, None)

        jobs = context.job_queue.get_jobs_by_name(str(user_id))
        for job in jobs:
            job.schedule_removal()

        await show_dashboard(update, context)


# ================= MESSAGE HANDLER =================
async def handle_wa_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await maintenance_guard(update, context):
        return

    user_id = update.effective_user.id
    text = update.message.text.strip()

    # 🔒 Pairing masih aktif → cegah spam
    if PAIRING_ACTIVE.get(user_id):
        # Command lain → abaikan
        if text.startswith("/"):
            return

        # Selain command → peringatan keras
        await update.message.reply_text(
            "⚠️ **_Pairing sedang berjalan_!**\n\n"
            "Gunakan tombol *Cancel Pairing* jika ingin membatalkan.",
            parse_mode="Markdown"
        )
        return

    # Hanya layani jika user memang sedang diminta kirim nomor
    if USER_STATES.get(user_id) != "WAITING_NUMBER":
        return

    # Validasi input nomor sederhana
    if not text.isdigit() or len(text) < 10:
        return await update.message.reply_text(
           "❌ Format nomor salah.\n"
           "Gunakan angka saja (misal: 62812345678)"
        )

    context.user_data['pending_number'] = text

    # Set state ke Pairing Active
    USER_STATES.pop(user_id, None)
    PAIRING_ACTIVE[user_id] = True
    token = str(uuid.uuid4())
    PAIRING_TOKEN[user_id] = token

    if context.user_data.get("change_sender"):
        msg = await update.message.reply_text(
            "🔄 **Mengganti akun WhatsApp**\n\n"
            "Session lama akan diputus,\n"
            "lalu menghubungkan ke nomor baru.\n\n"
            "_Mohon tunggu…_",
            parse_mode="Markdown"
        )
        try:
            requests.get(
                f"{WA_API}/logout",
                params={"userId": user_id},
                timeout=5
            )
        except:
              pass

        clear_session(user_id)
        await asyncio.sleep(1.5)

    else:
         msg = await update.message.reply_text(
             "⏳ _Menghubungkan ke WhatsApp Server_...",
             parse_mode="Markdown"
         )

    try:
        res = requests.get(
            f"{WA_API}/pair",
            params={"userId": user_id, "number": text},
            timeout=40
        ).json()

        if not res.get("ok"):
            PAIRING_ACTIVE.pop(user_id, None)
            return await msg.edit_text(
                f"❌ Gagal: {res.get('error', 'Server tidak merespon')}",
                reply_markup=kb_owner(),
                parse_mode="Markdown"
            )
        if context.user_data.get("change_sender"):
            kb = None
        else:
            kb = [[InlineKeyboardButton("❌ Cancel Pairing", callback_data="wa_cancel_pairing")]]

        await msg.edit_text(
            f"🔑 **KODE PAIRING**\n"
            f"👉 kode :`{res['code']}`\n\n"
            f"📱 Nomor: `{text}`\n"
            f"⏳ Berlaku: 90 detik",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )

        LAST_PAIR_MSG[user_id] = msg.message_id

        context.job_queue.run_repeating(
            check_status_job, # pastikan fungsi check_status_job sudah ada sesuai diskusi sebelumnya
            interval=5,
            first=5,
            name=str(user_id),
            data={"user_id": user_id, "token": token, "start": time.time(), "number": text}
        )

    except Exception as e:
        PAIRING_ACTIVE.pop(user_id, None)
        await msg.edit_text(
            "❌`gagal meminta kode pairing.` \n"
            "`kesalahan koneksi ke backend.`",
            reply_markup=kb_owner(),
            parse_mode="Markdown"
        )

# ================= JOB POLLING =================
async def check_status_job(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    user_id = job.data["user_id"]

    res = get_wa_status(user_id)

    # ✅ FIX UTAMA
    if res.get("online") and res.get("paired"):
        job.schedule_removal()
        PAIRING_ACTIVE.pop(user_id, None)

        app = context.application
        user_data = app.user_data.get(user_id)

        if isinstance(user_data, dict):
            user_data.pop("change_sender", None)

        number = res.get("number")
        if number:
            set_paired(user_id, number)
        try:
            await context.bot.delete_message(
                user_id,
                LAST_PAIR_MSG.get(user_id)
            )
        except:
            pass

        await context.bot.send_message(
            user_id,
            "✅ **WhatsApp berhasil terhubung!**\n\n"
            f"📱 Nomor : `{number}`\n"
            "📡 Status : `Online`",
            parse_mode="Markdown"
        )

        return

    # ⏰ Timeout 90 detik
    if time.time() - job.data["start"] > 90:
        job.schedule_removal()
        PAIRING_ACTIVE.pop(user_id, None)

        try:
            await context.bot.delete_message(
                user_id,
                LAST_PAIR_MSG.get(user_id)
            )
        except:
            pass

        await context.bot.send_message(
            user_id,
            "⏰ Waktu pairing habis. \nSilakan ulangi dengan /pairing."
        )

# ================= SETUP =================
def setup(app):
    app.add_handler(CommandHandler("pairing", pairing_command))
    app.add_handler(CallbackQueryHandler(handle_callback, pattern="^wa_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_wa_message))

