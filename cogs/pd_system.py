import discord
from discord.ext import commands
from discord import app_commands
import os, io, json, re
from PyPDF2 import PdfReader
from groq import AsyncGroq

class RPSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.groq = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
        self.txt_file_path = "manual_unificado.txt"
        self.cache_ejemplos = {}
        self.cache_plantillas = ""
        self.cache_roster = ""

    async def sync_manuales(self, guild, canal_respuesta):
        ch_manuales = discord.utils.get(guild.channels, name="manuales")
        if not ch_manuales:
            return await canal_respuesta.send("❌ No se encontró el canal `#manuales`.")
        
        await canal_respuesta.send("🔄 **Iniciando escaneo y transcripción de manuales...**")
        texto_consolidado = ""
        pdfs_encontrados = 0

        async for m in ch_manuales.history(limit=30):
            if m.content: 
                texto_consolidado += f"\n{m.content}\n"
            
            for att in m.attachments:
                if att.filename.endswith('.pdf'):
                    pdfs_encontrados += 1
                    try:
                        pdf_bytes = await att.read()
                        pdf = PdfReader(io.BytesIO(pdf_bytes))
                        texto_pdf = ""
                        for page in pdf.pages:
                            try:
                                text = page.extract_text()
                                if text: texto_pdf += text + "\n"
                            except Exception:
                                pass
                        
                        texto_consolidado += f"\n--- INICIO {att.filename} ---\n{texto_pdf}\n--- FIN {att.filename} ---\n"
                        await canal_respuesta.send(f"✅ **{att.filename}** procesado.")
                    except Exception as e:
                        await canal_respuesta.send(f"⚠️ Error procesando **{att.filename}**: Corrupto.")

        if texto_consolidado.strip():
            with open(self.txt_file_path, "w", encoding="utf-8") as f:
                f.write(texto_consolidado)
            await canal_respuesta.send(
                f"📂 **Sincronización terminada.** ({pdfs_encontrados} PDFs procesados).", 
                file=discord.File(self.txt_file_path)
            )
        else:
            await canal_respuesta.send("⚠️ No se encontró texto válido.")

    async def leer_manuales_txt(self, guild):
        if not os.path.exists(self.txt_file_path):
            return "No hay manuales cargados. Ejecuta /sincronizar_manuales."
        with open(self.txt_file_path, "r", encoding="utf-8") as f:
            return f.read()

    async def cargar_plantillas_globales(self, guild):
        if self.cache_plantillas: return self.cache_plantillas
        ch_plantillas = discord.utils.get(guild.channels, name="plantillas")
        texto_plantillas = ""
        if ch_plantillas:
            async for m in ch_plantillas.history(limit=20):
                if m.content: texto_plantillas += f"\n--- PLANTILLA OFICIAL ---\n{m.content}\n"
        self.cache_plantillas = texto_plantillas
        return self.cache_plantillas

    async def cargar_roster_global(self, guild):
        if self.cache_roster: return self.cache_roster
        ch_roster = discord.utils.get(guild.channels, name="roster-global")
        texto_roster = ""
        if ch_roster:
            # Lee hasta 100 mensajes por si tienes pegada la lista de toda la comisaría en varios mensajes
            async for m in ch_roster.history(limit=100):
                if m.content: texto_roster += f"\n{m.content}\n"
        self.cache_roster = texto_roster
        return self.cache_roster

    async def enviar_texto_largo(self, canal, texto, msg_original=None):
        pedazos = [texto[i:i+1900] for i in range(0, len(texto), 1900)]
        for idx, pedazo in enumerate(pedazos):
            if idx == 0 and msg_original:
                await msg_original.reply(pedazo)
            else:
                await canal.send(pedazo)

    @app_commands.command(name="setup_global", description="[ADMIN] Crea la categoría maestra y canales de sistema.")
    @app_commands.default_permissions(administrator=True)
    async def setup_global(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        g = interaction.guild

        cat = discord.utils.get(g.categories, name="⚙️ SISTEMA RP")
        if not cat: cat = await g.create_category("⚙️ SISTEMA RP")

        for ch_name, desc in [
            ("manuales", "📚 **CANAL DE MANUALES GLOBALES**\nSube aquí los PDFs con las leyes."),
            ("plantillas", "📌 **CANAL DE PLANTILLAS GLOBALES**\nPega aquí los formatos vacíos de informes."),
            ("roster-global", "👥 **BASE DE DATOS DE LA COMISARÍA**\nPega aquí la lista completa de TODOS los oficiales, usen o no el bot, con sus rangos. El bot la usará para reconocer nombres en capturas y ordenarlos de mayor a menor.")
        ]:
            ch = discord.utils.get(g.channels, name=ch_name)
            if not ch:
                ch = await g.create_text_channel(ch_name, category=cat)
                await ch.send(desc)

        await interaction.followup.send("✅ Canales maestros creados con éxito.")

    @app_commands.command(name="sincronizar_manuales", description="Fuerza la transcripción de todos los PDFs de #manuales.")
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
        ch_i = await g.create_text_channel("📋-informes", category=cat)
        ch_n = await g.create_text_channel("💭-registro-y-dudas", category=cat)

        try:
            await u.edit(nick=f"[{rango}] {nombre_personaje}"[:32])
        except discord.Forbidden:
            pass

        await ch_n.send(f"👋 **ESPACIO DE TRABAJO**\n{u.mention} Pide ordenamientos, internas o escribe 'redacta el informe'.")
        await interaction.followup.send(f"✅ Canales listos: {cat.jump_url}")

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot: return

        if msg.channel.name == "manuales" and msg.attachments:
            await self.sync_manuales(msg.guild, msg.channel)
            return
            
        if msg.channel.name == "plantillas":
            self.cache_plantillas = ""
            await msg.add_reaction("✅")
            return
            
        if msg.channel.name == "roster-global":
            self.cache_roster = "" # Actualiza la caché si pegas nuevos oficiales
            await msg.add_reaction("✅")
            return

        if msg.channel.name == "💭-registro-y-dudas":
            await msg.add_reaction("👀")
            
            async with msg.channel.typing():
                try:
                    imagen_analisis = ""
                    if msg.attachments:
                        for att in msg.attachments:
                            if att.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                                try:
                                    vision_res = await self.groq.chat.completions.create(
                                        messages=[{
                                            "role": "user", 
                                            "content": [
                                                {"type": "text", "text": "Extrae detalladamente todo el texto, tablas y nombres en formato de lista de esta imagen. Si ves nombres de personas, anótalos exactamente como aparecen."},
                                                {"type": "image_url", "image_url": {"url": att.url}}
                                            ]
                                        }],
                                        model="llama-3.2-11b-vision-preview"
                                    )
                                    imagen_analisis += f"\n[Datos de imagen]:\n{vision_res.choices[0].message.content}\n"
                                except Exception:
                                    pass

                    manuales_texto = await self.leer_manuales_txt(msg.guild)
                    plantillas_texto = await self.cargar_plantillas_globales(msg.guild)
                    roster_texto = await self.cargar_roster_global(msg.guild)
                    historial_chat = "\n".join([f"{m.author.display_name}: {m.content}" async for m in msg.channel.history(limit=10) if not m.author.bot])

                    frases_informe = ["redacta el informe", "genera el informe", "redáctame un informe", "redacta un informe"]
                    es_peticion_informe = any(frase in msg.content.lower() for frase in frases_informe)

                    sys_prompt = f"""
                    Eres un sistema de procesamiento de datos policiales. NO ERES CONVERSACIONAL.
                    
                    MANUALES Y CÓDIGOS: {manuales_texto[:4000]}
                    PLANTILLAS OFICIALES: {plantillas_texto[:3000]}
                    BASE DE DATOS DE LA COMISARÍA (ROSTER GLOBAL): {roster_texto[:4000]}
                    DATOS DE IMÁGENES RECIENTES: {imagen_analisis}
                    CONTEXTO RECIENTE: {historial_chat}
                    
                    REGLAS ABSOLUTAS:
                    1. ORDENAMIENTO DE OFICIALES: Si el usuario te manda nombres o una imagen y te pide ordenarlos, BUSCA a esas personas en la "BASE DE DATOS DE LA COMISARÍA". Usa los rangos especificados allí para ordenarlos estrictamente de MAYOR a MENOR rango. Incluye el rango o abreviatura.
                    2. PRECISIÓN: Solo devuelve el texto exacto que se te pide. Si es un código, da el significado corto. Si es un ordenamiento, da solo la lista ordenada.
                    3. INFORMES: Si el usuario dice "redacta el informe", toma la plantilla oficial y rellénala.
                    """

                    res = await self.groq.chat.completions.create(
                        messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": msg.content if msg.content else "Procesa la imagen."}],
                        model="llama-3.3-70b-versatile",
                        temperature=0.0
                    )

                    respuesta = res.choices[0].message.content

                    if es_peticion_informe:
                        cat = msg.channel.category
                        if cat:
                            ch_i = discord.utils.get(cat.channels, name="📋-informes")
                            if ch_i:
                                texto_informe = f"📋 **INFORME:**\n\n{respuesta}"
                                await self.enviar_texto_largo(ch_i, texto_informe)
                                await msg.remove_reaction("👀", self.bot.user)
                                await msg.add_reaction("✅")
                                return await msg.reply("✅ Informe enviado.")

                    await msg.remove_reaction("👀", self.bot.user)
                    await msg.add_reaction("✅")
                    await self.enviar_texto_largo(msg.channel, respuesta, msg_original=msg)

                except Exception as e:
                    await msg.remove_reaction("👀", self.bot.user)
                    await msg.add_reaction("❌")
                    await msg.reply(f"⚠️ **Error:** `{e}`")

async def setup(bot):
    await bot.add_cog(RPSystem(bot))
