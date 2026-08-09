import discord
from discord.ext import commands
from discord import app_commands
import os, io, asyncio
from PyPDF2 import PdfReader
from groq import AsyncGroq

class RPSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.groq = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
        self.cache_plantillas = ""
        self.cache_roster = ""
        self.cache_leyes = ""
        self.cache_correcciones = ""

    async def enviar_texto_largo(self, canal, texto, msg_original=None):
        """Corta el texto para no romper el límite de Discord y lo envía."""
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
        
        await canal_respuesta.send("🔄 **Procesando PDFs y transcribiéndolos a texto visible...**")
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
            # Limpia el canal de leyes viejo y sube la nueva transcripción
            await ch_leyes.purge(limit=100)
            await self.enviar_texto_largo(ch_leyes, f"**TRANSCRIPCIÓN DE LEYES Y MANUALES:**\n{texto_consolidado}")
            self.cache_leyes = "" # Obliga a recargar la caché
            await canal_respuesta.send(f"✅ **Sincronización terminada.** Revisa el canal {ch_leyes.mention} para ver cómo quedó la lectura de la IA.")
        else:
            await canal_respuesta.send("⚠️ No se encontró texto válido en los PDFs.")

    async def cargar_canal(self, guild, nombre_canal, limite=100):
        """Función maestra para leer cualquier canal como base de datos."""
        canal = discord.utils.get(guild.channels, name=nombre_canal)
        texto = ""
        if canal:
            async for m in canal.history(limit=limite, oldest_first=True):
                if m.content: texto += f"\n{m.content}\n"
        return texto

    async def auto_actualizar_roster(self, guild, datos_imagen):
        ch_roster = discord.utils.get(guild.channels, name="roster-global")
        if not ch_roster: return
        
        roster_msg = None
        async for m in ch_roster.history(limit=10):
            if "ESCALA JERÁRQUICA" in m.content:
                roster_msg = m
                break
        if not roster_msg: return

        sys_prompt = f"""
        Actualiza el siguiente ROSTER ACTUAL usando los NUEVOS DATOS.
        ROSTER ACTUAL: {roster_msg.content}
        NUEVOS DATOS: {datos_imagen}
        Agrega oficiales nuevos al final y actualiza el rango de los existentes si fueron ascendidos.
        Devuelve SOLO el texto completo actualizado.
        """
        try:
            res = await self.groq.chat.completions.create(
                messages=[{"role": "system", "content": sys_prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.0
            )
            nuevo_roster = res.choices[0].message.content.replace("```text", "").replace("```", "").strip()
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
            ("manuales", "📚 **CARGA DE PDFS**\nSube los PDFs. El bot los leerá y los transcribirá."),
            ("leyes-transcritas", "📜 **BASE DE DATOS DE LEYES (TEXTO)**\nAquí el bot escribe lo que lee de los PDFs. Puedes editar estos mensajes para corregir el formato o pegar tú mismo el código penal para mayor precisión."),
            ("correcciones-ia", "⚠️ **ACLARACIONES Y CORRECCIONES PARA LA IA**\nLo que escribas aquí tiene PRIORIDAD ABSOLUTA. Si la IA se confunde con una ley, acláraselo aquí."),
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
        ch_i = await g.create_text_channel("📋-informes", category=cat)
        ch_n = await g.create_text_channel("💭-registro-y-dudas", category=cat)

        try:
            await u.edit(nick=f"[{rango}] {nombre_personaje}"[:32])
        except discord.Forbidden:
            pass

        await ch_n.send(f"👋 **ESPACIO DE TRABAJO**\n{u.mention} Pide reportes o resuelve dudas aquí.")
        await interaction.followup.send(f"✅ Canales listos.")

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot: return

        # Auto-sincronizar si suben un PDF nuevo
        if msg.channel.name == "manuales" and msg.attachments:
            if any(a.filename.endswith('.pdf') for a in msg.attachments):
                await self.sync_manuales(msg.guild, msg.channel)
            return
            
        # Limpieza de caché inteligente al editar bases de datos
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
                    
                    if msg.attachments:
                        for att in msg.attachments:
                            if att.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                                try:
                                    vision_res = await self.groq.chat.completions.create(
                                        messages=[{
                                            "role": "user", 
                                            "content": [
                                                {"type": "text", "text": "Transcribe todos los textos y datos relevantes de esta imagen."},
                                                {"type": "image_url", "image_url": {"url": att.url}}
                                            ]
                                        }],
                                        model="llama-3.2-11b-vision-preview"
                                    )
                                    imagen_analisis += f"\n[Datos de imagen]:\n{vision_res.choices[0].message.content}\n"
                                    tiene_nombres = True
                                except Exception:
                                    pass

                    if tiene_nombres:
                        asyncio.create_task(self.auto_actualizar_roster(msg.guild, imagen_analisis))

                    # Cargar TODO el contexto sin límites que asfixien a la IA (Capacidad de Llama 3: 128k tokens)
                    if not self.cache_leyes: self.cache_leyes = await self.cargar_canal(msg.guild, "leyes-transcritas", 50)
                    if not self.cache_correcciones: self.cache_correcciones = await self.cargar_canal(msg.guild, "correcciones-ia", 20)
                    if not self.cache_plantillas: self.cache_plantillas = await self.cargar_canal(msg.guild, "plantillas", 20)
                    if not self.cache_roster: self.cache_roster = await self.cargar_canal(msg.guild, "roster-global", 20)
                    
                    historial_chat = "\n".join([f"{m.author.display_name}: {m.content}" async for m in msg.channel.history(limit=10) if not m.author.bot])
                    es_informe = any(frase in msg.content.lower() for frase in ["redacta el informe", "genera el informe"])

                    sys_prompt = f"""
                    Eres un sistema policial estricto y de alta precisión.
                    
                    --- BASE DE DATOS LEYES (Lee descripciones y sanciones, NO solo títulos) ---
                    {self.cache_leyes[:80000]}
                    
                    --- REGLAS ABSOLUTAS Y CORRECCIONES DE LA COMANDANCIA ---
                    {self.cache_correcciones}
                    
                    --- OTROS DATOS ---
                    PLANTILLAS: {self.cache_plantillas[:3000]}
                    ROSTER: {self.cache_roster[:3000]}
                    IMÁGENES: {imagen_analisis}
                    CONTEXTO RECIENTE DEL CHAT DE ESTE OFICIAL: {historial_chat}
                    
                    INSTRUCCIONES CLAVE:
                    1. PRIORIDAD: Si hay un conflicto entre la 'BASE DE DATOS LEYES' y las 'REGLAS ABSOLUTAS', obedece SIEMPRE a las Reglas Absolutas.
                    2. PRECISIÓN DE LEYES: Cuando te pregunten qué aplicar, lee detalladamente el contexto del crimen en los artículos, no te guíes solo por el título.
                    3. RESPUESTAS: Sé militar, frío y directo. Devuelve el artículo y la condena EXACTA sin charlar.
                    4. INFORMES: Si piden redactar, usa las plantillas.
                    """

                    res = await self.groq.chat.completions.create(
                        messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": msg.content if msg.content else "Analiza el contexto."}],
                        model="llama-3.3-70b-versatile",
                        temperature=0.0
                    )

                    respuesta = res.choices[0].message.content

                    if es_informe:
                        cat = msg.channel.category
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
                    await msg.reply(f"⚠️ **Error:** `{e}`")

async def setup(bot):
    await bot.add_cog(RPSystem(bot))
