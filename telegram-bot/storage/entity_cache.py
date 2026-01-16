import json, os

CACHE_FILE = os.path.join(os.path.dirname(__file__), "entity_cache.json")

def load():
    if not os.path.exists(CACHE_FILE):
        return {}
    with open(CACHE_FILE, "r") as f:
        return json.load(f)

def save(data):
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2)

def add(entity):
    data = load()
    data[f"-100{entity.id}"] = {
        "id": entity.id,
        "access_hash": getattr(entity, "access_hash", None),
        "username": entity.username,
        "title": getattr(entity, "title", "-"),
        "private": entity.username is None
    }
    save(data)

def get(entity_id):
    return load().get(entity_id)




