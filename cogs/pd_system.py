import discord
from discord.ext import commands
from discord import app_commands
import os, io, asyncio
from PyPDF2 import PdfReader
from google import genai
from google.genai import types

class RPSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.cache_plantillas = ""
        self.cache_roster = ""
        self.cache_leyes = ""
        self.cache_correcciones = ""
        self.cache_ejemplos = {}

    async def enviar_texto_largo(self, canal, texto, msg_original=None):
        pedazos = [texto[i:i+1900] for i in range(0, len(texto), 1900)]
        for idx, pedazo in enumerate(pedazos):
            if idx == 0 and msg_original:
                await msg_original.reply(pedazo)
            else:
                await canal.send(pedazo)

    async def sync_manuales(self, guild, canal_respuesta):
        ch_manuales = discord.utils.get(guild.channels, name="manuales")
        ch_leyes = discord.utils.get(guild.channels, name="leyes-transcritas")
        
        if not ch_manuales or not ch_leyes:
            return await canal_respuesta.send("❌ Faltan los canales `#manuales` o `#leyes-transcritas`.")
        
        await canal_respuesta.send("🔄 **Procesando PDFs con Gemini y transcribiéndolos...**")
        texto_consolidado = ""
        pdfs_encontrados = 0

        async for m in ch_manuales.history(limit=50):
            for att in m.attachments:
                if att.filename.endswith('.pdf'):
                    pdfs_encontrados += 1
                    try:
                        pdf_bytes = await att.read()
                        pdf = PdfReader(io.BytesIO(pdf_bytes))
                        for page in pdf.pages:
                            try:
                                text = page.extract_text()
                                if text: texto_consolidado += text + "\n\n"
                            except Exception:
                                pass
                    except Exception:
                        await canal_respuesta.send(f"⚠️ Error procesando **{att.filename}**.")

        if texto_consolidado.strip():
            await ch_leyes.purge(limit=100)
            await self.enviar_texto_largo(ch_leyes, f"**TRANSCRIPCIÓN DE LEYES Y MANUALES:**\n{texto_consolidado}")
            self.cache_leyes = ""
            await canal_respuesta.send(f"✅ **Sincronización terminada.** Revisa el canal {ch_leyes.mention}.")
        else:
            await canal_respuesta.send("⚠️ No se encontró texto válido en los PDFs.")

    async def cargar_canal(self, guild, nombre_canal, limite=100):
        canal = discord.utils.get(guild.channels, name=nombre_canal)
        texto = ""
        if canal:
            async for m in canal.history(limit=limite, oldest_first=True):
                if m.content: texto += f"\n{m.content}\n"
        return texto

    async def cargar_ejemplos_usuario(self, ch_ejemplos):
        ch_id = ch_ejemplos.id
        if ch_id in self.cache_ejemplos:
            return self.cache_ejemplos[ch_id]

        textos_ejemplos = ""
        async for m in ch_ejemplos.history(limit=15):
            if not m.author.bot and m.content:
                textos_ejemplos += f"\n--- EJEMPLO DE INFORME ---\n{m.content}\n"
        
        self.cache_ejemplos[ch_id] = textos_ejemplos
        return self.cache_ejemplos[ch_id]

    async def auto_actualizar_roster(self, guild, datos_imagen):
        ch_roster = discord.utils.get(guild.channels, name="roster-global")
        if not ch_roster: return
        
        roster_msg = None
        async for m in ch_roster.history(limit=10):
            if "ESCALA JERÁRQUICA" in m.content:
                roster_msg = m
                break
        if not roster_msg: return

        prompt_roster = f"""
        Actualiza el siguiente ROSTER ACTUAL usando los NUEVOS DATOS.
        ROSTER ACTUAL: {roster_msg.content}
        NUEVOS DATOS: {datos_imagen}
        Agrega oficiales nuevos al final y actualiza el rango de los existentes si fueron ascendidos.
        Devuelve SOLO el texto completo actualizado en texto plano.
        """
        try:
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt_roster,
                config=types.GenerateContentConfig(temperature=0.0)
            )
            nuevo_roster = response.text.replace("```text", "").replace("```", "").strip()
            if roster_msg.author == self.bot.user:
                await roster_msg.edit(content=nuevo_roster)
            else:
                await roster_msg.delete()
                await ch_roster.send(nuevo_roster)
            self.cache_roster = ""
        except Exception:
            pass

    @app_commands.command(name="setup_global", description="[ADMIN] Crea la categoría maestra y canales de sistema.")
    @app_commands.default_permissions(administrator=True)
    async def setup_global(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        g = interaction.guild

        cat = discord.utils.get(g.categories, name="⚙️ SISTEMA RP")
        if not cat: cat = await g.create_category("⚙️ SISTEMA RP")

        canales = [
            ("manuales", "📚 **CARGA DE PDFS**\nSube los PDFs. El bot los leerá y transcribirá."),
            ("leyes-transcritas", "📜 **BASE DE DATOS DE LEYES (TEXTO)**\nAquí el bot escribe lo que lee de los PDFs."),
            ("correcciones-ia", "⚠️ **ACLARACIONES Y CORRECCIONES PARA LA IA**\nLo que escribas aquí tiene PRIORIDAD ABSOLUTA sobre las leyes."),
            ("plantillas", "📌 **PLANTILLAS GLOBALES**\nPega aquí los formatos vacíos."),
            ("roster-global", "👥 **BASE DE DATOS COMISARÍA**\nPega aquí la jerarquía y oficiales.")
        ]

        for ch_name, desc in canales:
            ch = discord.utils.get(g.channels, name=ch_name)
            if not ch:
                ch = await g.create_text_channel(ch_name, category=cat)
                await ch.send(desc)

        await interaction.followup.send("✅ Canales maestros creados con éxito.")

    @app_commands.command(name="sincronizar_manuales", description="Fuerza la transcripción de PDFs a #leyes-transcritas.")
    async def cmd_sincronizar(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.sync_manuales(interaction.guild, interaction.channel)

    @app_commands.command(name="alta_personaje", description="Crea tus canales de trabajo.")
    async def alta(self, interaction: discord.Interaction, nombre_personaje: str, faccion: str, rango: str):
        await interaction.response.defer(ephemeral=True)
        g, u = interaction.guild, interaction.user
        
        nombre_rol = f"{faccion} | {rango} - {nombre_personaje}"
        nuevo_rol = await g.create_role(name=nombre_rol, reason="Alta RP", color=discord.Color.dark_theme())
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

        try:
            await u.edit(nick=f"[{rango}] {nombre_personaje}"[:32])
        except discord.Forbidden:
            pass

        await ch_e.send(f"📌 **BASE DE APRENDIZAJE**\n{u.mention} Pega aquí tus informes pasados para que la IA aprenda tu estilo exacto de redacción.")
        await ch_n.send(f"👋 **ESPACIO DE TRABAJO**\n{u.mention} Pide reportes o resuelve dudas aquí.")
        await interaction.followup.send(f"✅ Canales listos.")

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot: return

        if msg.channel.name == "manuales" and msg.attachments:
            if any(a.filename.endswith('.pdf') for a in msg.attachments):
                await self.sync_manuales(msg.guild, msg.channel)
            return
            
        if msg.channel.name == "📚-ejemplos-pasados":
            if msg.channel.id in self.cache_ejemplos:
                del self.cache_ejemplos[msg.channel.id]
            await msg.add_reaction("✅")
            return

        if msg.channel.name in ["plantillas", "roster-global", "leyes-transcritas", "correcciones-ia"]:
            if msg.channel.name == "plantillas": self.cache_plantillas = ""
            if msg.channel.name == "roster-global": self.cache_roster = ""
            if msg.channel.name == "leyes-transcritas": self.cache_leyes = ""
            if msg.channel.name == "correcciones-ia": self.cache_correcciones = ""
            await msg.add_reaction("✅")
            return

        if msg.channel.name == "💭-registro-y-dudas":
            await msg.add_reaction("👀")
            
            async with msg.channel.typing():
                try:
                    imagen_analisis = ""
                    tiene_nombres = False
                    image_parts = []
                    
                    if msg.attachments:
                        for att in msg.attachments:
                            if att.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                                try:
                                    img_bytes = await att.read()
                                    image_parts.append(
                                        types.Part.from_bytes(data=img_bytes, mime_type=att.content_type or "image/jpeg")
                                    )
                                    tiene_nombres = True
                                except Exception:
                                    pass

                    if tiene_nombres and image_parts:
                        vis_resp = self.client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=[image_parts[0], "Transcribe todos los textos, nombres y rangos de esta imagen con total precisión."]
                        )
                        imagen_analisis = f"\n[Datos de imagen]:\n{vis_resp.text}\n"
                        asyncio.create_task(self.auto_actualizar_roster(msg.guild, imagen_analisis))

                    # Cargar bases de datos desde los canales globales
                    if not self.cache_leyes: self.cache_leyes = await self.cargar_canal(msg.guild, "leyes-transcritas", 100)
                    if not self.cache_correcciones: self.cache_correcciones = await self.cargar_canal(msg.guild, "correcciones-ia", 30)
                    if not self.cache_plantillas: self.cache_plantillas = await self.cargar_canal(msg.guild, "plantillas", 20)
                    if not self.cache_roster: self.cache_roster = await self.cargar_canal(msg.guild, "roster-global", 30)
                    
                    # Cargar ejemplos específicos del canal del oficial
                    cat = msg.channel.category
                    textos_ejemplos = ""
                    if cat:
                        ch_e = discord.utils.get(cat.channels, name="📚-ejemplos-pasados")
                        if ch_e:
                            textos_ejemplos = await self.cargar_ejemplos_usuario(ch_e)

                    historial_chat = "\n".join([f"{m.author.display_name}: {m.content}" async for m in msg.channel.history(limit=10) if not m.author.bot])
                    es_informe = any(frase in msg.content.lower() for frase in ["redacta el informe", "genera el informe"])

                    system_instruction = f"""
                    Eres un sistema policial estricto, formal y de alta precisión para un servidor de Roleplay.
                    
                    --- BASE DE DATOS LEYES ---
                    {self.cache_leyes}
                    
                    --- REGLAS ABSOLUTAS Y CORRECCIONES DE LA COMANDANCIA ---
                    {self.cache_correcciones}
                    
                    --- PLANTILLAS OFICIALES ---
                    {self.cache_plantillas}
                    
                    --- ROSTER DE LA COMISARÍA ---
                    {self.cache_roster}
                    
                    --- EJEMPLOS DE ESTILO Y FORMATO DE ESTE OFICIAL ---
                    {textos_ejemplos}
                    """

                    user_prompt = f"""
                    Contexto e imágenes recientes:
                    {imagen_analisis}
                    
                    Historial reciente del chat:
                    {historial_chat}
                    
                    Pregunta o petición del oficial:
                    {msg.content if msg.content else "Analiza el contenido adjunto."}
                    
                    REGLAS:
                    1. Si hay conflicto entre leyes y las 'REGLAS ABSOLUTAS Y CORRECCIONES', obedece las correcciones.
                    2. Lee bien las descripciones de los artículos antes de responder.
                    3. Si te piden redactar un informe, además de usar la plantilla, ADAPTA el estilo, formato y vocabulario a los "EJEMPLOS DE ESTILO" que este oficial subió a su canal de aprendizaje.
                    4. Sé frío, directo y conciso para dudas. Extiéndete únicamente al redactar informes.
                    """

                    contents = [user_prompt]
                    if image_parts:
                        contents.append(image_parts[0])

                    response = self.client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=contents,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.0
                        )
                    )

                    respuesta = response.text

                    if es_informe:
                        if cat:
                            ch_i = discord.utils.get(cat.channels, name="📋-informes")
                            if ch_i:
                                await self.enviar_texto_largo(ch_i, f"📋 **INFORME:**\n\n{respuesta}")
                                await msg.remove_reaction("👀", self.bot.user)
                                await msg.add_reaction("✅")
                                return await msg.reply("✅ Informe enviado.")

                    await msg.remove_reaction("👀", self.bot.user)
                    await msg.add_reaction("✅")
                    await self.enviar_texto_largo(msg.channel, respuesta, msg_original=msg)

                except Exception as e:
                    await msg.remove_reaction("👀", self.bot.user)
                    await msg.add_reaction("❌")
                    await msg.reply(f"⚠️ **Error con Gemini:** `{e}`")

async def setup(bot):
    await bot.add_cog(RPSystem(bot))
