import json
import os

DATABASE_FILE = "global_database.json"

def get_guild_data(guild_id):
    if not os.path.exists(DATABASE_FILE):
        return {}
    with open(DATABASE_FILE, "r") as f:
        data = json.load(f)
    return data.get(str(guild_id), {})

def save_guild_data(guild_id, guild_data):
    data = {}
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, "r") as f:
            data = json.load(f)
    data[str(guild_id)] = guild_data
    with open(DATABASE_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_config(guild_id, key, default=None):
    data = get_guild_data(guild_id)
    return data.get("config", {}).get(key, default)

def tiene_permiso(user):
    # Solo tú (administradores) tienen permiso para cosas críticas
    return user.guild_permissions.administrator
