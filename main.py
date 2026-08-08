import discord
from discord.ext import commands, tasks
import os
import random
import asyncio
import time
import aiohttp
import webserver

# Cargamos el .env SOLO si existe (para pruebas locales).
# En Render, esto se ignora y usa las variables del dashboard.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
URL_RENDER = os.getenv("URL_RENDER")

class RoguePhoenixBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True 
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # CARGA MODULAR: Lee todos los archivos de la carpeta cogs
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f"📦 Módulo cargado: {filename}")
                except Exception as e:
                    print(f"❌ Error cargando {filename}: {e}")

bot = RoguePhoenixBot()

# ===================================================================
# --- TAREA DE AUTO-PING FANTASMA PARA ENGAÑAR A RENDER ---
# ===================================================================

# Orígenes Falsos: Fingimos venir desde estas páginas
REFERERS = [
    "https://www.google.com/",
    "https://www.bing.com/",
    "https://duckduckgo.com/",
    "https://twitter.com/",
    "https://discord.com/"
]

# Disfraces: Windows, Mac, Linux, iPhone y Android
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 OPR/109.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Mobile Safari/537.36"
]

@tasks.loop(minutes=10)
async def auto_ping():
    if not URL_RENDER:
        print("⚠️ Advertencia: URL_RENDER no configurada. El autoping está inactivo.")
        return

    try:
        # Evasión Cronométrica Absoluta: Espera entre 1 y 580 segundos al azar
        await asyncio.sleep(random.randint(1, 580))
        
        # Rompe-Cachés Dinámico: Crea una URL única cada vez (ej: ?v=8473&t=16900000)
        cache_buster = f"?v={random.randint(1000, 9999)}&t={int(time.time())}"
        target_url = URL_RENDER + cache_buster
        
        async with aiohttp.ClientSession() as session:
            # Construcción de un perfil humano completo
            headers = {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": random.choice(["es-MX,es;q=0.9", "es-ES,es;q=0.9,en;q=0.8", "en-US,en;q=0.9"]),
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "cross-site",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
                "Referer": random.choice(REFERERS)
            }
            
            async with session.get(target_url, headers=headers) as response:
                if response.status == 200:
                    print("🔄 Auto-ping 'Fantasma' exitoso. Render engañado.")
                else:
                    print(f"⚠️ Auto-ping devolvió código: {response.status}")
    except Exception as e:
        print(f"⚠️ Error en auto-ping: {e}")
# ===================================================================

@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")
    
    # Arrancamos el auto-ping solo si no está corriendo ya
    if URL_RENDER and not auto_ping.is_running():
        auto_ping.start()
    
    try:
        synced = await bot.tree.sync()
        print(f"🔄 Auto-Sincronización: {len(synced)} comandos slash (/) cargados correctamente.")
    except Exception as e:
        print(f"❌ Error al sincronizar comandos: {e}")

# Comando para recargar un módulo sin apagar el bot
@bot.command(name="reload")
@commands.has_permissions(administrator=True)
async def reload_cog(ctx, cog_name: str):
    try:
        await bot.reload_extension(f"cogs.{cog_name}")
        await ctx.send(f"✅ Módulo `cogs/{cog_name}.py` recargado con éxito.")
    except Exception as e:
        await ctx.send(f"❌ Error recargando módulo: {e}")

if __name__ == "__main__":
    if not TOKEN:
        print("❌ ERROR: No se encontró el BOT_TOKEN en las variables de entorno.")
    else:
        # Arrancamos el servidor web para Render
        webserver.keep_alive(bot)
        # Arrancamos el bot
        bot.run(TOKEN)
