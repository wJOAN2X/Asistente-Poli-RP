import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite, os, io, json, re
from PyPDF2 import PdfReader
from groq import AsyncGroq

class RPSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "pd_database.db"
        self.groq = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

    async def cog_load(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''CREATE TABLE IF NOT EXISTS usuarios (discord_id TEXT PRIMARY KEY, personaje TEXT, faccion TEXT, rango TEXT, categoria_id TEXT, ch_ejemplos TEXT, ch_informes TEXT, ch_notas TEXT, rol_id TEXT)''')
            await db.execute('''CREATE TABLE IF NOT EXISTS personajes_lore (nombre TEXT PRIMARY KEY, faccion TEXT, rango TEXT, historial TEXT)''')
            await db.execute('''CREATE TABLE IF NOT EXISTS manuales (nombre TEXT PRIMARY KEY, contenido TEXT)''')
            await db.execute('''CREATE TABLE IF NOT EXISTS config (clave TEXT PRIMARY KEY, valor TEXT)''')
            await db.commit()

    async def get_config_ch(self, clave):
        async with aiosqlite.connect(self.db_path) as db:
            res = await db.execute("SELECT valor FROM config WHERE clave=?", (clave,))
            row = await res.fetchone()
            return int(row[0]) if row else None

    async def hacer_backup(self):
        backup_ch_id = await self.get_config_ch("canal_backup")
        if backup_ch_id:
            canal = self.bot.get_channel(backup_ch_id)
            if canal:
                try:
                    await canal.send("📦 **Backup de Seguridad de la DB Global:**", file=discord.File(self.db_path))
                except Exception:
                    pass

    @app_commands.command(name="rp_setup_canales", description="[ADMIN] Define canal de manuales globales y backups.")
    @app_commands.default_permissions(administrator=True)
    async def setup(self, interaction: discord.Interaction, canal_manuales: discord.TextChannel, canal_backup: discord.TextChannel):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT OR REPLACE INTO config (clave, valor) VALUES (?, ?)", ("canal_manuales", str(canal_manuales.id)))
            await db.execute("INSERT OR REPLACE INTO config (clave, valor) VALUES (?, ?)", ("canal_backup", str(canal_backup.id)))
            await db.commit()
        await interaction.response.send_message(f"✅ Canales configurados.\n📖 **Manuales:** {canal_manuales.mention}\n📦 **Backups:** {canal_backup.mention}")
        await self.hacer_backup()

    @app_commands.command(name="alta_personaje", description="Crea tus canales individuales de trabajo.")
    async def alta(self, interaction: discord.Interaction, nombre_personaje: str, faccion: str, rango: str):
        await interaction.response.defer(ephemeral=True)
        g, u = interaction.guild, interaction.user
        
        async with aiosqlite.connect(self.db_path) as db:
            if await (await db.execute("SELECT * FROM usuarios WHERE discord_id = ?", (str(u.id),))).fetchone():
                return await interaction.followup.send("❌ Ya tienes tus canales creados.")

            nombre_rol = f"{faccion} | {rango} - {nombre_personaje}"
            nuevo_rol = await g.create_role(name=nombre_rol, reason="Alta Individual", color=discord.Color.dark_theme())
            await u.add_roles(nuevo_rol)

            ow = {
                g.default_role: discord.PermissionOverwrite(read_messages=False),
                nuevo_rol: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
                g.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
            }
            
            cat = await g.create_category(nombre_rol, overwrites=ow)
            ch_e = await g.create_text_channel("📚-ejemplos-pasados", category=cat)
            ch_i = await g.create_text_channel("📋-informes", category=cat)
            ch_n = await g.create_text_channel("💭-registro-y-dudas", category=cat)

            await ch_e.send(f"📌 **TU BASE DE APRENDIZAJE**\n{u.mention} Pega aquí informes del pasado. La IA imitará tu estilo.")
            await ch_n.send(f"👋 **TU ESPACIO DE TRABAJO**\n{u.mention} Sube capturas o notas. Escribe `redacta el informe` para generarlo.")
            
            await db.execute("INSERT INTO usuarios VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (str(u.id), nombre_personaje, faccion, rango, str(cat.id), str(ch_e.id), str(ch_i.id), str(ch_n.id), str(nuevo_rol.id)))
            await db.execute("INSERT OR REPLACE INTO personajes_lore (nombre, faccion, rango, historial) VALUES (?, ?, ?, ?)", (nombre_personaje, faccion, rango, "Registrado en DB."))
            await db.commit()
            
        await interaction.followup.send(f"✅ Canales listos: {cat.jump_url}")
        await self.hacer_backup()

    @app_commands.command(name="borrar_historial", description="Limpia tu contexto de memoria a corto plazo.")
    async def borrar_historial(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        u = interaction.user
        async with aiosqlite.connect(self.db_path) as db:
            usuario = await (await db.execute("SELECT ch_ejemplos, ch_notas FROM usuarios WHERE discord_id = ?", (str(u.id),))).fetchone()
            if not usuario:
                return await interaction.followup.send("❌ No estás registrado.")
            try:
                ch_e = self.bot.get_channel(int(usuario[0]))
                ch_n = self.bot.get_channel(int(usuario[1]))
                if ch_e: await ch_e.purge(limit=100)
                if ch_n: await ch_n.purge(limit=100)
                await ch_e.send("🧹 **Canal limpiado.**")
                await ch_n.send("🧹 **Memoria borrada.**")
            except Exception:
                return await interaction.followup.send("⚠️ Error: Necesito permisos de 'Gestionar Mensajes'.")
            await interaction.followup.send("✅ Historial purgado.")

    async def extraer_y_actualizar_lore_global(self, texto_o_imagen, msg_ref):
        prompt = "Extrae nombres, facción, rango y actos en JSON estricto. Ejemplo: [{\"nombre\": \"Juan\", \"faccion\": \"PD\", \"rango\": \"Oficial\", \"nuevo_historial\": \"Arrestó a alguien\"}]"
        try:
            res = await self.groq.chat.completions.create(
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": texto_o_imagen}],
                model="llama-3.3-70b-versatile", temperature=0.1
            )
            match = re.search(r'\[.*\]', res.choices[0].message.content, re.DOTALL)
            if match:
                datos = json.loads(match.group(0))
                async with aiosqlite.connect(self.db_path) as db:
                    for d in datos:
                        nombre = d.get("nombre")
                        if not nombre: continue
                        faccion = d.get("faccion", "Desconocida")
                        rango = d.get("rango", "Desconocido")
                        accion = d.get("nuevo_historial", "")
                        
                        row = await (await db.execute("SELECT historial FROM personajes_lore WHERE nombre=?", (nombre,))).fetchone()
                        if row:
                            nh = row[0] + f" | {accion}"[-1500:]
                            await db.execute("UPDATE personajes_lore SET faccion=?, rango=?, historial=? WHERE nombre=?", (faccion, rango, nh, nombre))
                        else:
                            await db.execute("INSERT INTO personajes_lore (nombre, faccion, rango, historial) VALUES (?, ?, ?, ?)", (nombre, faccion, rango, accion))
                    await db.commit()
        except Exception as e:
            pass

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot: return

        # 1. MANUALES
        man_ch = await self.get_config_ch("canal_manuales")
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

        # 2. EL BLINDAJE ANTI-WIPES (Detectamos el nombre del canal directo desde Discord)
        if msg.channel.name == "💭-registro-y-dudas":
            # REACCIÓN INSTANTÁNEA PARA QUE SEPAS QUE EL BOT NO ESTÁ MUERTO
            await msg.add_reaction("👀")

            async with aiosqlite.connect(self.db_path) as db:
                usuario = await (await db.execute("SELECT * FROM usuarios WHERE ch_notas = ?", (str(msg.channel.id),))).fetchone()

            # SI RENDER BORRÓ LA BASE DE DATOS, EL BOT SE AUTO-SANA
            if not usuario:
                cat = msg.channel.category
                if cat:
                    ch_e = discord.utils.get(cat.channels, name="📚-ejemplos-pasados")
                    ch_i = discord.utils.get(cat.channels, name="📋-informes")
                    if ch_e and ch_i:
                        async with aiosqlite.connect(self.db_path) as db:
                            await db.execute("INSERT OR REPLACE INTO usuarios (discord_id, personaje, faccion, rango, categoria_id, ch_ejemplos, ch_informes, ch_notas, rol_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (str(msg.author.id), msg.author.display_name, "Recuperado", "N/A", str(cat.id), str(ch_e.id), str(ch_i.id), str(msg.channel.id), "N/A"))
                            await db.commit()
                        async with aiosqlite.connect(self.db_path) as db:
                            usuario = await (await db.execute("SELECT * FROM usuarios WHERE ch_notas = ?", (str(msg.channel.id),))).fetchone()
                        await msg.channel.send("🔄 **Sistema Anti-Wipes:** Render me había borrado la memoria, pero he leído la estructura de tu categoría y me he auto-configurado de nuevo. Operativo al 100%.")
                    else:
                        await msg.remove_reaction("👀", self.bot.user)
                        await msg.add_reaction("❌")
                        await msg.channel.send("⚠️ Error crítico: Render me borró la memoria y me faltan los canales originales de esta categoría para auto-sanarme.")
                        return

            contenido_analizar = msg.content

            if msg.attachments and any(a.filename.endswith(('.mp3', '.wav', '.ogg', '.m4a')) for a in msg.attachments):
                async with msg.channel.typing():
                    try:
                        res = await self.groq.audio.transcriptions.create(file=(msg.attachments[0].filename, await msg.attachments[0].read()), model="whisper-large-v3", response_format="text")
                        contenido_analizar += f"\nAudio: {res}"
                        await msg.reply(f"🎙️ **Audio procesado:**\n{res}")
                    except Exception as e:
                        await msg.reply(f"❌ Error procesando audio: `{e}`")

            if msg.attachments and any(a.filename.endswith(('.png', '.jpg', '.jpeg')) for a in msg.attachments):
                async with msg.channel.typing():
                    try:
                        res = await self.groq.chat.completions.create(messages=[{"role": "user", "content": [{"type": "text", "text": "Describe todo lo que ves relevante para el rol."}, {"type": "image_url", "image_url": {"url": msg.attachments[0].url}}]}], model="llama-3.2-11b-vision-preview")
                        contenido_analizar += f"\nVisual: {res.choices[0].message.content}"
                        await msg.reply("👁️ **Captura procesada en la DB.**")
                    except Exception as e:
                        await msg.reply(f"❌ Error procesando imagen: `{e}`")

            if contenido_analizar.strip():
                await self.extraer_y_actualizar_lore_global(contenido_analizar, msg)

            if "informe" in msg.content.lower() or "redacta" in msg.content.lower():
                await msg.add_reaction("⏳")
                async with msg.channel.typing():
                    try:
                        textos_ejemplos = ""
                        ch_e = self.bot.get_channel(int(usuario[5])) 
                        if ch_e:
                            async for m in ch_e.history(limit=10):
                                if not m.author.bot and m.content: textos_ejemplos += f"\n--- EJEMPLO ---\n{m.content}\n"

                        async with aiosqlite.connect(self.db_path) as db:
                            lore = "\n".join([f"[{row[0]}] {row[1]} {row[2]} - Historial: {row[3]}" for row in await (await db.execute("SELECT nombre, faccion, rango, historial FROM personajes_lore")).fetchall()])
                            manuales = "\n".join([row[0] for row in await (await db.execute("SELECT contenido FROM manuales")).fetchall()])

                        historial_chat = "\n".join([m.content async for m in msg.channel.history(limit=12) if not m.author.bot])
                        
                        sys_prompt = f"Asistente de Roleplay.\nINSTRUCCIONES: Imita el tono y formato de los EJEMPLOS.\nEJEMPLOS:\n{textos_ejemplos}\nBASE DATOS GLOBAL:\n{lore[-2000:]}\nLEYES:\n{manuales[:3000]}\nSITUACIÓN ACTUAL A REDACTAR:\n{historial_chat}"
                        
                        res = await self.groq.chat.completions.create(messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": msg.content}], model="llama-3.3-70b-versatile")
                        
                        await self.bot.get_channel(int(usuario[6])).send(f"📋 **INFORME GENERADO DINÁMICAMENTE:**\n\n{res.choices[0].message.content}")
                        await msg.remove_reaction("⏳", self.bot.user)
                        await msg.add_reaction("✅")
                        await msg.reply("✅ Informe redactado. Revísalo en tu canal de informes.")
                    except Exception as e:
                        await msg.remove_reaction("⏳", self.bot.user)
                        await msg.add_reaction("❌")
                        await msg.reply(f"⚠️ **Error fatal conectando con la IA:**\n`{e}`")
                        
            elif "duda" in msg.content.lower():
                await msg.add_reaction("⏳")
                async with msg.channel.typing():
                    try:
                        async with aiosqlite.connect(self.db_path) as db:
                            manuales = "\n".join([row[0] for row in await (await db.execute("SELECT contenido FROM manuales")).fetchall()])
                        sys_prompt = f"Asistente de normativas unificadas. Responde usando esto: {manuales[:4000]}"
                        res = await self.groq.chat.completions.create(messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": msg.content}], model="llama-3.3-70b-versatile")
                        await msg.remove_reaction("⏳", self.bot.user)
                        await msg.reply(res.choices[0].message.content)
                    except Exception as e:
                        await msg.remove_reaction("⏳", self.bot.user)
                        await msg.add_reaction("❌")
                        await msg.reply(f"⚠️ **Error resolviendo duda:**\n`{e}`")

async def setup(bot):
    await bot.add_cog(RPSystem(bot))
