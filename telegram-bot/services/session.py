import json
import os
import time
from threading import Lock

# ⛔ PATH TETAP SESUAI PERMINTAAN
SESSION_FILE = "/data/data/com.termux/files/home/shared/sessions.json"

FILE_LOCK = Lock()

# ================= FILE IO =================
def load_sessions():
    with FILE_LOCK:
        if not os.path.exists(SESSION_FILE):
            return {}
        try:
            with open(SESSION_FILE, "r") as f:
                return json.load(f)
        except:
            return {}

def save_sessions(data):
    with FILE_LOCK:
        with open(SESSION_FILE, "w") as f:
            json.dump(data, f, indent=2)

# ================= SESSION =================
def set_paired(telegram_id, wa_number):
    data = load_sessions()
    sid = str(telegram_id)

    if sid not in data:
        data[sid] = {}

    data[sid].update({
        "paired": True,
        "wa_number": wa_number,
        "paired_at": int(time.time())
    })

    save_sessions(data)

def clear_session(telegram_id):
    """
    Logout WA tapi MODE tetap disimpan
    """
    data = load_sessions()
    sid = str(telegram_id)

    if sid in data:
        data[sid]["paired"] = False
        data[sid].pop("wa_number", None)

    save_sessions(data)

def get_session(telegram_id):
    return load_sessions().get(str(telegram_id), {})

def is_paired(telegram_id):
    return get_session(telegram_id).get("paired", False)

# ================= MODE =================
def save_user_mode(telegram_id, mode):
    ALLOWED = {"Slow", "Medium", "Fast"}
    if mode not in ALLOWED:
        mode = "Medium"

    data = load_sessions()
    sid = str(telegram_id)

    if sid not in data:
        data[sid] = {}

    data[sid]["cek_mode"] = mode
    save_sessions(data)

def get_user_mode(telegram_id):
    return get_session(telegram_id).get("cek_mode", "Medium")

# ================= RUNTIME STATE (RAM) =================
USER_STATES = {}
PAIRING_ACTIVE = {}
PAIRING_TOKEN = {}
PAIRING_JOBS = {}
LAST_PAIR_MSG = {}


