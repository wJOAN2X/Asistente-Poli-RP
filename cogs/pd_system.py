import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite, os, io, json, re
from PyPDF2 import PdfReader
from groq import AsyncGroq

class RPSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "pd_database.db" # Mantenemos el nombre del archivo DB por compatibilidad
        self.groq = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

    async def cog_load(self):
        async with aiosqlite.connect(self.db_path) as db:
            # Tablas Universales de Roleplay
            await db.execute('''CREATE TABLE IF NOT EXISTS usuarios (discord_id TEXT PRIMARY KEY, personaje TEXT, faccion TEXT, rango TEXT, categoria_id TEXT, ch_plantillas TEXT, ch_informes TEXT, ch_notas TEXT, rol_id TEXT)''')
            await db.execute('''CREATE TABLE IF NOT EXISTS personajes_lore (nombre TEXT PRIMARY KEY, faccion TEXT, rango TEXT, historial TEXT)''')
            await db.execute('''CREATE TABLE IF NOT EXISTS plantillas (nombre TEXT PRIMARY KEY, formato TEXT)''')
            await db.execute('''CREATE TABLE IF NOT EXISTS manuales (nombre TEXT PRIMARY KEY, contenido TEXT)''')
            await db.execute('''CREATE TABLE IF NOT EXISTS config (clave TEXT PRIMARY KEY, valor TEXT)''')
            
            # Pre-cargamos la plantilla de Carreras Ilegales basada en el Manual Oficial
            plantilla_carreras = """
Distribución del TAC: [Mandos]
Coches involucrados:
- [VEHICULO] | [COLOR] | [MATRICULA] | [ESTADO/CONDUCTOR]
Descripción de lo sucedido:
- [BREVE DESCRIPCIÓN]
- [INICIO Y FIN DE CARRERA]
- [VEHÍCULOS EXTERNOS]
Sujetos Detenidos: [NOMBRES Y COCHES]
Objetos Retirados: [OBJETOS]
"""
            await db.execute("INSERT OR IGNORE INTO plantillas (nombre, formato) VALUES (?, ?)", ("carrera_ilegal", plantilla_carreras))
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
                    await canal.send("📦 **Backup Automático de la DB Global:**", file=discord.File(self.db_path))
                except Exception as e:
                    print(f"Error subiendo backup: {e}")

    # =====================================================================
    # COMANDOS ADMINISTRATIVOS Y DE CONFIGURACIÓN
    # =====================================================================

    @app_commands.command(name="rp_setup_canales", description="[ADMIN] Define canal de manuales y backups.")
    @app_commands.default_permissions(administrator=True)
    async def setup(self, interaction: discord.Interaction, canal_manuales: discord.TextChannel, canal_backup: discord.TextChannel):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT OR REPLACE INTO config (clave, valor) VALUES (?, ?)", ("canal_manuales", str(canal_manuales.id)))
            await db.execute("INSERT OR REPLACE INTO config (clave, valor) VALUES (?, ?)", ("canal_backup", str(canal_backup.id)))
            await db.commit()
        await interaction.response.send_message(f"✅ Canales globales configurados.\n📖 **Manuales/Lore:** {canal_manuales.mention}\n📦 **Backups:** {canal_backup.mention}")
        await self.hacer_backup()

    @app_commands.command(name="plantilla_add", description="[ADMIN] Añade una nueva plantilla para los informes.")
    @app_commands.default_permissions(administrator=True)
    async def add_plantilla(self, interaction: discord.Interaction, nombre: str, formato: str):
        nombre = nombre.lower().replace(" ", "_")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT OR REPLACE INTO plantillas (nombre, formato) VALUES (?, ?)", (nombre, formato))
            await db.commit()
        await interaction.response.send_message(f"✅ Plantilla `{nombre}` guardada correctamente en la Base de Datos Global.")
        await self.hacer_backup()

    # =====================================================================
    # COMANDO PÚBLICO: ALTA DE CUALQUIER PERSONAJE (Banda, PD, Civil, EMS)
    # =====================================================================

    @app_commands.command(name="alta_personaje", description="Crea tu espacio de trabajo. Válido para todas las facciones.")
    async def alta(self, interaction: discord.Interaction, nombre_personaje: str, faccion: str, rango: str):
        await interaction.response.defer(ephemeral=True)
        g, u = interaction.guild, interaction.user
        
        async with aiosqlite.connect(self.db_path) as db:
            if await (await db.execute("SELECT * FROM usuarios WHERE discord_id = ?", (str(u.id),))).fetchone():
                return await interaction.followup.send("❌ Ya estás registrado en el sistema global.")

            nombre_rol = f"{faccion} | {rango} - {nombre_personaje}"
            nuevo_rol = await g.create_role(name=nombre_rol, reason="Alta en DB Global", color=discord.Color.dark_theme())
            await u.add_roles(nuevo_rol)

            ow = {
                g.default_role: discord.PermissionOverwrite(read_messages=False),
                nuevo_rol: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
                g.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
            }
            
            cat = await g.create_category(nombre_rol, overwrites=ow)
            ch_p = await g.create_text_channel("📝-plantillas", category=cat)
            ch_i = await g.create_text_channel("📋-informes", category=cat)
            ch_n = await g.create_text_channel("💭-registro-y-dudas", category=cat)

            # Inyectamos las plantillas disponibles en su canal de plantillas
            plantillas = await (await db.execute("SELECT nombre, formato FROM plantillas")).fetchall()
            if plantillas:
                texto_plantillas = "**PLANTILLAS DISPONIBLES EN LA BASE DE DATOS:**\n\n"
                for p_nombre, p_formato in plantillas:
                    texto_plantillas += f"**{p_nombre}**\n```\n{p_formato}\n```\n"
                await ch_p.send(texto_plantillas)

            await ch_n.send(f"{u.mention} Este es tu canal de registro. Sube capturas o anota lo que ocurre. La IA analizará a los involucrados y actualizará la base de datos global. Cuando necesites un informe, di `Genera informe usando plantilla [nombre]`.")
            
            await db.execute("INSERT INTO usuarios VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (str(u.id), nombre_personaje, faccion, rango, str(cat.id), str(ch_p.id), str(ch_i.id), str(ch_n.id), str(nuevo_rol.id)))
            await db.execute("INSERT OR REPLACE INTO personajes_lore (nombre, faccion, rango, historial) VALUES (?, ?, ?, ?)", (nombre_personaje, faccion, rango, "Personaje registrado en el sistema."))
            await db.commit()
            
        await interaction.followup.send(f"✅ Espacio de trabajo creado: {cat.jump_url}")
        await self.hacer_backup()

    # =====================================================================
    # MOTOR DE INTELIGENCIA Y BASE DE DATOS
    # =====================================================================

    async def extraer_y_actualizar_lore(self, texto_o_imagen):
        """Motor invisible que lee el rol y actualiza rangos/facciones en la DB"""
        prompt_extraccion = """
        Analiza la información proporcionada (texto o análisis de imagen).
        Identifica a los personajes de Roleplay mencionados. 
        Si se menciona su facción, rango, o algún acto importante (ej. arresto, ascenso, disparo, venta de drogas), extráelo.
        DEVUELVE ÚNICA Y EXCLUSIVAMENTE UN ARRAY JSON VÁLIDO. SIN TEXTO ANTES NI DESPUÉS.
        Formato:
        [{"nombre": "Juan Perez", "faccion": "Ballas", "rango": "Lider", "nuevo_historial": "Visto vendiendo drogas en Grove St"}]
        """
        try:
            res = await self.groq.chat.completions.create(
                messages=[{"role": "system", "content": prompt_extraccion}, {"role": "user", "content": texto_o_imagen}],
                model="llama3-70b-8192",
                temperature=0.1
            )
            
            json_str = res.choices[0].message.content
            # Limpiar posible markdown
            match = re.search(r'\[.*\]', json_str, re.DOTALL)
            if match:
                datos = json.loads(match.group(0))
                async with aiosqlite.connect(self.db_path) as db:
                    for d in datos:
                        nombre = d.get("nombre")
                        if not nombre: continue
                        faccion = d.get("faccion", "Desconocida")
                        rango = d.get("rango", "Desconocido")
                        accion = d.get("nuevo_historial", "")
                        
                        # Buscar si ya existe
                        row = await (await db.execute("SELECT historial FROM personajes_lore WHERE nombre=?", (nombre,))).fetchone()
                        if row:
                            nuevo_historial = row[0] + f" | {accion}"[-1500:] # Límite de caracteres
                            await db.execute("UPDATE personajes_lore SET faccion=?, rango=?, historial=? WHERE nombre=?", (faccion, rango, nuevo_historial, nombre))
                        else:
                            await db.execute("INSERT INTO personajes_lore (nombre, faccion, rango, historial) VALUES (?, ?, ?, ?)", (nombre, faccion, rango, accion))
                    await db.commit()
                return True
        except Exception as e:
            print(f"Error en extracción invisible: {e}")
            return False

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot: return
        man_ch = await self.get_config_ch("canal_manuales")

        # 1. Leer Lore / Documentos globales
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

        # 2. Revisar si es un canal de registro de algún usuario
        async with aiosqlite.connect(self.db_path) as db:
            usuario = await (await db.execute("SELECT * FROM usuarios WHERE ch_notas = ?", (str(msg.channel.id),))).fetchone()
        
        if usuario:
            contenido_analizar = msg.content

            # Procesar Audios
            if msg.attachments and any(a.filename.endswith(('.mp3', '.wav', '.ogg', '.m4a')) for a in msg.attachments):
                async with msg.channel.typing():
                    res = await self.groq.audio.transcriptions.create(file=(msg.attachments[0].filename, await msg.attachments[0].read()), model="whisper-large-v3", response_format="text")
                    contenido_analizar += f"\nTranscripción de audio: {res}"
                    await msg.reply(f"🎙️ **Audio procesado:**\n{res}")

            # Procesar Capturas de pantalla
            if msg.attachments and any(a.filename.endswith(('.png', '.jpg', '.jpeg')) for a in msg.attachments):
                async with msg.channel.typing():
                    res = await self.groq.chat.completions.create(messages=[{"role": "user", "content": [{"type": "text", "text": "Describe todo lo que ves relevante para un servidor de roleplay. Nombres, acciones, items."}, {"type": "image_url", "image_url": {"url": msg.attachments[0].url}}]}], model="llama-3.2-11b-vision-preview")
                    contenido_analizar += f"\nAnálisis visual: {res.choices[0].message.content}"
                    await msg.reply(f"👁️ **Captura procesada en la DB.**")

            # === PASO 1: EXTRACCIÓN INVISIBLE Y ACTUALIZACIÓN DE LORE ===
            if contenido_analizar.strip():
                await self.extraer_y_actualizar_lore(contenido_analizar)

            # === PASO 2: REDACCIÓN DE INFORMES BASADOS EN PLANTILLAS ===
            if "informe" in msg.content.lower():
                async with msg.channel.typing():
                    async with aiosqlite.connect(self.db_path) as db:
                        # Recuperar plantillas y lore de personajes
                        plantillas = "\n".join([f"Plantilla [{row[0]}]:\n{row[1]}" for row in await (await db.execute("SELECT nombre, formato FROM plantillas")).fetchall()])
                        lore = "\n".join([f"[{row[0]}] {row[1]} {row[2]} - Historial: {row[3]}" for row in await (await db.execute("SELECT nombre, faccion, rango, historial FROM personajes_lore")).fetchall()])
                        manuales = "\n".join([row[0] for row in await (await db.execute("SELECT contenido FROM manuales")).fetchall()])

                    historial_chat = "\n".join([m.content async for m in msg.channel.history(limit=10) if not m.author.bot])
                    
                    sys_prompt = f"""
                    Eres el motor central de un servidor de Roleplay. 
                    
                    BASES DE DATOS ACTUALES:
                    -- LORE DE PERSONAJES:
                    {lore[-3000:]}
                    
                    -- PLANTILLAS DE INFORMES:
                    {plantillas}
                    
                    -- NORMATIVAS LOCALES:
                    {manuales[:3000]}
                    
                    TAREA:
                    El usuario te ha pedido un informe. Revisa el historial reciente del chat:
                    {historial_chat}
                    
                    Identifica qué plantilla quiere usar. Rellena esa plantilla EXACTA utilizando la información del chat y el LORE de los personajes si están implicados. No inventes datos que no estén en el contexto.
                    """
                    res = await self.groq.chat.completions.create(messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": msg.content}], model="llama3-70b-8192")
                    
                    await self.bot.get_channel(int(usuario[6])).send(f"📋 **INFORME GENERADO:**\n\n{res.choices[0].message.content}")
                    await msg.reply("✅ El informe ha sido generado y adaptado a tu formato. Enviado a tu canal de informes.")
                    
            elif "duda" in msg.content.lower():
                async with msg.channel.typing():
                    async with aiosqlite.connect(self.db_path) as db:
                        manuales = "\n".join([row[0] for row in await (await db.execute("SELECT contenido FROM manuales")).fetchall()])
                    sys_prompt = f"Eres un asistente experto en normativas de Roleplay. Responde la duda basándote en esto: {manuales[:4000]}"
                    res = await self.groq.chat.completions.create(messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": msg.content}], model="llama3-70b-8192")
                    await msg.reply(res.choices[0].message.content)

async def setup(bot):
    await bot.add_cog(RPSystem(bot))
