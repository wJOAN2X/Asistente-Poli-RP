import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import json
import aiohttp
import random
import asyncio
import time
import logging
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

# ================= TUS IMPORTS ORIGINALES =================
try:
    from config import GLOBAL_BACKUP_CHANNEL_ID, DATABASE_FILE
except ImportError:
    pass
from utils.database import tiene_permiso, save_guild_data, get_guild_data
import utils.database as db

# --- SILENCIAR EL SPAM DE LOGS DE SUPABASE (HTTPX) ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger("httpx").setLevel(logging.WARNING)

# ================= NUEVOS IMPORTS STREAMS =================
try:
    from streams_bot import StreamsBotManager
except ImportError:
    StreamsBotManager = None
# ==========================================================

class RoguePhoenixBot(commands.Bot):
    def __init__(self):
        # Usamos '!' como prefijo para comandos normales como !sync
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True 
        super().__init__(command_prefix="!", intents=intents)
        self.paneles_cargados = False

    async def setup_hook(self):
        # Carga de Cogs dinámica (Cargará tickets.py, pd_system.py, economia.py, etc.)
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f"📦 Módulo cargado con éxito: {filename}")
                except Exception as e:
                    print(f"❌ Error cargando {filename}: {e}")

bot = RoguePhoenixBot()

# ================= INICIALIZACIÓN STREAMS =================
if StreamsBotManager:
    streams_manager = StreamsBotManager(db, webserver)
# ==========================================================

# ===================================================================
# --- TAREA DE AUTO-PING FANTASMA PARA ENGAÑAR A RENDER ---
# ===================================================================
REFERERS = [
    "https://www.google.com/",
    "https://www.bing.com/",
    "https://duckduckgo.com/",
    "https://twitter.com/",
    "https://discord.com/"
]

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
        await asyncio.sleep(random.randint(1, 580))
        cache_buster = f"?v={random.randint(1000, 9999)}&t={int(time.time())}"
        target_url = URL_RENDER + cache_buster
        
        async with aiohttp.ClientSession() as session:
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
    
    if URL_RENDER and not auto_ping.is_running():
        auto_ping.start()

    # 🚀 FIX: AUTO-SINCRONIZACIÓN MÁGICA 
    try:
        synced = await bot.tree.sync()
        print(f"🔄 Auto-Sincronización: {len(synced)} comandos cargados correctamente en Discord.")
    except Exception as e:
        print(f"❌ Error en la Auto-Sincronización: {e}")
        
    # --- BLOQUE DE AUTOCARGA VISUAL DE MENÚS (PROTEGIDO) ---
    if not bot.paneles_cargados:
        try:
            from cogs.economia import actualizar_todos_los_paneles
            from cogs.robos import actualizar_pizarron_robos
            
            for guild in bot.guilds:
                print(f"🔄 Autocargando menús para el servidor: {guild.name}")
                await actualizar_todos_los_paneles(guild)
                await actualizar_pizarron_robos(guild)
                
            print("✅ Todos los menús vinculados y actualizados visualmente con la DB.")
            bot.paneles_cargados = True 
        except Exception as e:
            print(f"⚠️ Aviso autocargando menús (Ignorar si no existen los cogs): {e}")

    # ================= ARRANQUE DEL BUCLE STREAMS =================
    if StreamsBotManager:
        try:
            await streams_manager.iniciar()
        except Exception as e:
            print(f"⚠️ Error arrancando streams: {e}")
    # ==============================================================


# ================= COMANDOS DE PREFIJO (!) =================

@bot.command(name="sync")
@commands.has_permissions(administrator=True)
async def sync_command(ctx):
    """Comando manual para forzar la sincronización de slash commands (/)"""
    await ctx.send("🔄 Sincronizando comandos... (Esto puede tardar unos segundos)")
    try:
        bot.tree.copy_global_to(guild=ctx.guild)
        synced = await bot.tree.sync(guild=ctx.guild)
        await ctx.send(f"✅ ¡Sincronización exitosa! Se activaron **{len(synced)}** comandos slash (/) en este servidor.")
    except Exception as e:
        await ctx.send(f"❌ Error al sincronizar: {e}")

@bot.command(name="reload")
@commands.has_permissions(administrator=True)
async def reload_cog(ctx, cog_name: str):
    """Recarga un módulo específico sin reiniciar el bot"""
    try:
        await bot.reload_extension(f"cogs.{cog_name}")
        await ctx.send(f"✅ Módulo `cogs/{cog_name}.py` recargado con éxito.")
    except Exception as e:
        await ctx.send(f"❌ Error recargando módulo: {e}")

# 🚀 FIX: COMANDO DE EMERGENCIA PARA VER POR QUÉ FALLAN LOS TICKETS
@bot.command(name="test_tickets")
@commands.has_permissions(administrator=True)
async def test_tickets(ctx):
    await ctx.send("🔍 Analizando el archivo `tickets.py`...")
    try:
        await bot.load_extension('cogs.tickets')
        await ctx.send("✅ El archivo estaba apagado, pero lo acabo de encender sin errores.")
    except commands.ExtensionAlreadyLoaded:
        try:
            await bot.reload_extension('cogs.tickets')
            await ctx.send("✅ El archivo se recargó perfectamente. No hay errores de código.")
        except Exception as e:
            error_msg = f"❌ **ERROR AL RECARGAR TICKETS:**\n```py\n{e}\n```"
            await ctx.send(error_msg)
    except commands.ExtensionNotFound:
        await ctx.send("❌ **ERROR CRÍTICO:** No encuentro el archivo. ¿Seguro que se llama `tickets.py` y está adentro de la carpeta `cogs`?")
    except Exception as e:
        error_msg = f"❌ **EL CÓDIGO DE TICKETS EXPLOTÓ POR ESTO:**\n```py\n{e}\n```"
        await ctx.send(error_msg)


# ================= COMANDOS DE BARRA (/) =================

@bot.tree.command(name="restore_backup", description="[ADMIN] Restaura base de datos desde un JSON (Global o Local).")
async def restore_backup(interaction: discord.Interaction, archivo: discord.Attachment):
    await interaction.response.defer(ephemeral=True)
    
    if not tiene_permiso(interaction.user):
        return await interaction.followup.send("⛔ Permiso denegado.", ephemeral=True)
        
    if not archivo.filename.endswith('.json'):
        return await interaction.followup.send("❌ El archivo debe ser formato .json", ephemeral=True)
        
    try:
        contenido = await archivo.read()
        data = json.loads(contenido.decode('utf-8'))
        
        servers_restaurados = 0
        es_global = any(str(k).isdigit() for k in data.keys())
        
        if es_global:
            for guild_id_str, guild_data in data.items():
                if str(guild_id_str).isdigit(): 
                    save_guild_data(guild_id_str, guild_data)
                    servers_restaurados += 1
                    # FIX: Pequeña pausa para no bloquear el bot si el JSON es enorme
                    await asyncio.sleep(0.1) 
            await interaction.followup.send(f"✅ **Backup GLOBAL restaurado.** Se inyectó info en {servers_restaurados} servidores.", ephemeral=True)
        else:
            save_guild_data(interaction.guild.id, data)
            await interaction.followup.send("✅ **Backup LOCAL restaurado** con éxito.", ephemeral=True)
            
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


@bot.tree.command(name="refrescar_paneles", description="Fuerza a los menús a leer y mostrar los datos en vivo. (Público)")
async def refrescar_paneles(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        from cogs.economia import actualizar_todos_los_paneles
        from cogs.robos import actualizar_pizarron_robos
        
        await actualizar_todos_los_paneles(interaction.guild)
        await actualizar_pizarron_robos(interaction.guild)
        
        await interaction.followup.send("✅ Paneles actualizados con la base de datos.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


# ================== EL ESCUDO MAESTRO ==================
@bot.tree.interaction_check
async def check_modulos_apagados(interaction: discord.Interaction):
    # 1. Dejar pasar interacciones que NO sean en un servidor (ej. DMs)
    if not interaction.guild: return True 
    
    # 2. Dejar pasar interacciones que NO sean comandos (ej. botones, modales, selects)
    if interaction.type != discord.InteractionType.application_command:
        return True
        
    # 3. Solo revisamos los Slash Commands
    if interaction.command:
        
        # 🚀 FIX ANTI-LAG PARA MÚSICA: Dejamos pasar el comando 'play' inmediatamente
        if interaction.command.name == "play":
            return True

        gdb = get_guild_data(interaction.guild.id)
        modulos_apagados = gdb.get("modulos_apagados", {})
        
        comando_usado = interaction.command.name 
        
        relacion_modulos = {
            "robos": ["panel_robos", "setup_tabla_robos", "modificar_robo", "panel_capturas"],
            "ausencias": ["ausencia", "volver", "panel_ausencias", "ausencia_add", "ausencia_remove"],
            "plantacion": ["instalar_panel_plantacion", "plantacion_quemar_admin", "plantacion_resumen"],
            "economia": ["cuota_fac", "fondos_fac"],
            "tickets": ["panel_tickets", "ticket_configurar_rol", "ticket_configurar_log", "ticket_force_close"],
            "sistemas": ["diagnostico_streams", "backup_now", "forzar_bitacora", "registrar_cc", "gestion_cc", "panel_streams", "check_lives"]
        }
        
        modulo_del_comando = None
        for mod, comandos in relacion_modulos.items():
            if comando_usado in comandos:
                modulo_del_comando = mod
                break
                
        # Si el módulo está apagado, bloqueamos
        if modulo_del_comando and modulos_apagados.get(modulo_del_comando) == True:
            await interaction.response.send_message(f"⛔ **Módulo Desactivado:** El equipo de Administración ha deshabilitado el módulo de `{modulo_del_comando.upper()}` temporalmente en este servidor.", ephemeral=True)
            return False 
            
    # Si todo está bien, dejamos pasar el comando
    return True


# ================= ARRANQUE DEL SERVIDOR WEB Y BOT =================

if __name__ == "__main__":
    if not TOKEN:
        print("❌ ERROR CRÍTICO: No se encontró el BOT_TOKEN en las variables de entorno.")
    else:
        try:
            # Arrancamos la web en un hilo separado pasándole la instancia del bot
            webserver.keep_alive(bot)
            
            # Arrancamos el bot
            bot.run(TOKEN)
            
        except discord.errors.HTTPException as e:
            if e.status == 429: 
                print("\n[CRÍTICO] BLOQUEO 429 por Rate Limit de Discord.")
            else: 
                raise e
