import discord
from discord.ext import commands, tasks
import os
import random
import asyncio
import time
import aiohttp
from dotenv import load_dotenv
import webserver

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
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

# --- TAREA DE AUTO-PING FANTASMA ---
@tasks.loop(minutes=10)
async def auto_ping():
    try:
        await asyncio.sleep(random.randint(1, 100))
        cache_buster = f"?v={random.randint(1000, 9999)}&t={int(time.time())}"
        target_url = URL_RENDER + cache_buster
        
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/123.0.0.0"}
        async with aiohttp.ClientSession() as session:
            async with session.get(target_url, headers=headers) as response:
                if response.status == 200:
                    print("🔄 Auto-ping exitoso.")
    except Exception as e:
        print(f"⚠️ Error en auto-ping: {e}")

@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")
    if not auto_ping.is_running():
        auto_ping.start()
    
    try:
        synced = await bot.tree.sync()
        print(f"🔄 Auto-Sincronización: {len(synced)} comandos listos.")
    except Exception as e:
        print(f"❌ Error al sincronizar: {e}")

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
    webserver.keep_alive(bot)
    bot.run(TOKEN)
