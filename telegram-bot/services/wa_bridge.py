import json
import os
from config import BRIDGE_FILE

def read_bridge():
    if not os.path.exists(BRIDGE_FILE):
        return {}

    try:
        with open(BRIDGE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def get_wa_status(telegram_id):
    bridge = read_bridge()
    return bridge.get("sessions", {}).get(str(telegram_id), {})

