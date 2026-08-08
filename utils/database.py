import json
import os

DATABASE_FILE = "global_database.json"

def _load_data():
    """Función interna blindada para cargar el JSON sin que el bot crashee."""
    if not os.path.exists(DATABASE_FILE):
        return {}
    try:
        with open(DATABASE_FILE, "r", encoding="utf-8") as f:
            content = f.read()
            # Si el archivo existe pero está vacío, devuelve un diccionario vacío
            return json.loads(content) if content.strip() else {}
    except (json.JSONDecodeError, FileNotFoundError):
        # Si el JSON se corrompe por un apagón o error, no crashea el bot
        print("⚠️ Advertencia: global_database.json corrupto o no encontrado. Iniciando limpio.")
        return {}

def get_guild_data(guild_id):
    data = _load_data()
    return data.get(str(guild_id), {})

def save_guild_data(guild_id, guild_data):
    data = _load_data()
    data[str(guild_id)] = guild_data
    
    # Escritura segura: asegura que no se pierdan caracteres especiales
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_config(guild_id, key, default=None):
    data = get_guild_data(guild_id)
    return data.get("config", {}).get(key, default)

def tiene_permiso(user):
    # Solo tú (administradores) tienen permiso para cosas críticas
    return user.guild_permissions.administrator
