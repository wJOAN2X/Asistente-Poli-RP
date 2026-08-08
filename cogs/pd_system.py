import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite, os, io
from PyPDF2 import PdfReader
from groq import AsyncGroq

class PDSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "pd_database.db"
        self.groq = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

    async def cog_load(self):
        async with aiosqlite.connect(self.db_path) as db:
            # Añadida la columna 'rol_id' a la base de datos
            await db.execute('''CREATE TABLE IF NOT EXISTS oficiales (discord_id TEXT PRIMARY KEY, rango TEXT, categoria_id TEXT, ch_plantillas TEXT, ch_informes TEXT, ch_notas TEXT, rol_id TEXT)''')
            await db.execute('''CREATE TABLE IF NOT EXISTS manuales (nombre TEXT PRIMARY KEY, contenido TEXT)''')
            await db.execute('''CREATE TABLE IF NOT EXISTS config (clave TEXT PRIMARY KEY, valor TEXT)''')
            await db.commit()

    async def get_config_ch(self, clave):
        async with aiosqlite.connect(self.db_path) as db:
            res = await db.execute("SELECT valor FROM config WHERE clave=?", (clave,))
            row = await res.fetchone()
            return int(row[0]) if row else None

    # Función que envía el archivo .db al canal de backup de Discord
    async def hacer_backup(self):
        backup_ch_id = await self.get_config_ch("canal_backup")
        if backup_ch_id:
            canal = self.bot.get_channel(backup_ch_id)
            if canal:
                try:
                    await canal.send("📦 **Backup Automático de la DB:** (Descárgalo si Render borra los datos)", file=discord.File(self.db_path))
                except Exception as e:
                    print(f"Error subiendo backup: {e}")

    @app_commands.command(name="pd_setup_canales", description="[ADMIN] Define canal de manuales y canal de backups.")
    @app_commands.default_permissions(administrator=True)
    async def setup(self, interaction: discord.Interaction, canal_manuales: discord.TextChannel, canal_backup: discord.TextChannel):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT OR REPLACE INTO config (clave, valor) VALUES (?, ?)", ("canal_manuales", str(canal_manuales.id)))
            await db.execute("INSERT OR REPLACE INTO config (clave, valor) VALUES (?, ?)", ("canal_backup", str(canal_backup.id)))
            await db.commit()
        await interaction.response.send_message(f"✅ Configuración guardada.\n📖 **Manuales:** {canal_manuales.mention}\n📦 **Backups:** {canal_backup.mention}")
        await self.hacer_backup()

    @app_commands.command(name="pd_alta", description="Registra un oficial, le crea su Rol y sus canales.")
    async def alta(self, interaction: discord.Interaction, rango: str):
        await interaction.response.defer(ephemeral=True)
        g, u = interaction.guild, interaction.user
        
        async with aiosqlite.connect(self.db_path) as db:
            if await (await db.execute("SELECT * FROM oficiales WHERE discord_id = ?", (str(u.id),))).fetchone():
                return await interaction.followup.send("❌ Ya estás registrado en la PD.")

            # 1. Crear un ROL de Discord exclusivo para esta persona
            nombre_rol = f"🚓 {rango} - {u.display_name}"
            nuevo_rol = await g.create_role(name=nombre_rol, reason="Alta en PD Bot", color=discord.Color.blue())
            await u.add_roles(nuevo_rol)

            # 2. Los permisos de la categoría ahora se basan en el ROL creado, no en el usuario suelto
            ow = {
                g.default_role: discord.PermissionOverwrite(read_messages=False),
                nuevo_rol: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
                g.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
            }
            
            # 3. Crear canales
            cat = await g.create_category(nombre_rol, overwrites=ow)
            ch_p = await g.create_text_channel("📝-plantillas", category=cat)
            ch_i = await g.create_text_channel("📋-informes", category=cat)
            ch_n = await g.create_text_channel("💭-notas-y-dudas", category=cat)

            await ch_n.send(f"{u.mention} Se te asignó el rol {nuevo_rol.mention}. Sube tus pruebas aquí y pide tus informes.")
            
            # 4. Guardar absolutamente todo en la DB
            await db.execute("INSERT INTO oficiales VALUES (?, ?, ?, ?, ?, ?, ?)", (str(u.id), rango, str(cat.id), str(ch_p.id), str(ch_i.id), str(ch_n.id), str(nuevo_rol.id)))
            await db.commit()
            
        await interaction.followup.send(f"✅ Rol y Canales creados: {cat.jump_url}")
        
        # Guardar en la nube el nuevo usuario
        await self.hacer_backup()

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot: return
        man_ch = await self.get_config_ch("canal_manuales")

        # 1. Leer PDFs y crear Backup automático
        if man_ch and msg.channel.id == man_ch and msg.attachments:
            for att in msg.attachments:
                if att.filename.endswith('.pdf'):
                    await msg.add_reaction("⏳")
                    pdf = PdfReader(io.BytesIO(await att.read()))
                    texto = "\n".join([p.extract_text() for p in pdf.pages if p.extract_text()])
                    async with aiosqlite.connect(self.db_path) as db:
                        await db.execute("INSERT OR REPLACE INTO manuales VALUES (?, ?)", (att.filename, texto))
                        await db.commit()
                    await msg.add_reaction("✅")
            await self.hacer_backup()
            return

        # 2. Revisar si es el canal de notas privado
        async with aiosqlite.connect(self.db_path) as db:
            oficial = await (await db.execute("SELECT * FROM oficiales WHERE ch_notas = ?", (str(msg.channel.id),))).fetchone()
        
        if oficial:
            async with aiosqlite.connect(self.db_path) as db:
                manuales = "\n".join([row[0] for row in await (await db.execute("SELECT contenido FROM manuales")).fetchall()])

            # Audios
            if msg.attachments and any(a.filename.endswith(('.mp3', '.wav', '.ogg', '.m4a')) for a in msg.attachments):
                async with msg.channel.typing():
                    res = await self.groq.audio.transcriptions.create(file=(msg.attachments[0].filename, await msg.attachments[0].read()), model="whisper-large-v3", response_format="text")
                    return await msg.reply(f"🎙️ **Transcripción:**\n{res}")

            # Capturas
            if msg.attachments and any(a.filename.endswith(('.png', '.jpg', '.jpeg')) for a in msg.attachments):
                async with msg.channel.typing():
                    res = await self.groq.chat.completions.create(messages=[{"role": "user", "content": [{"type": "text", "text": "Extrae datos clave para reporte policial."}, {"type": "image_url", "image_url": {"url": msg.attachments[0].url}}]}], model="llama-3.2-11b-vision-preview")
                    return await msg.reply(f"👁️ **Análisis Visual:**\n{res.choices[0].message.content}")

            # Generar Informes / Dudas
            if "informe" in msg.content.lower() or "duda" in msg.content.lower():
                async with msg.channel.typing():
                    historial = "\n".join([m.content async for m in msg.channel.history(limit=15) if not m.author.bot])
                    sys_prompt = f"IA policial. Manuales: {manuales[:4000]}\nContexto: {historial}\nSi es duda, responde. Si es informe, redacta formalmente."
                    res = await self.groq.chat.completions.create(messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": msg.content}], model="llama3-70b-8192")
                    
                    if "informe" in msg.content.lower():
                        await self.bot.get_channel(int(oficial[4])).send(f"📋 **INFORME:**\n{res.choices[0].message.content}")
                        await msg.reply("✅ Informe generado en tu canal de informes.")
                    else:
                        await msg.reply(res.choices[0].message.content)

async def setup(bot):
    await bot.add_cog(PDSystem(bot))
