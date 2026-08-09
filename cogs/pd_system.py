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
        self.txt_file_path = "manual_unificado.txt"
        self.cache_plantillas = ""
        self.cache_roster = ""

    async def sync_manuales(self, guild, canal_respuesta):
        ch_manuales = discord.utils.get(guild.channels, name="manuales")
        if not ch_manuales:
            return await canal_respuesta.send("❌ No se encontró el canal `#manuales`.")
        
        await canal_respuesta.send("🔄 **Generando Backup y transcribiendo PDFs (esto puede tardar unos segundos)...**")
        texto_consolidado = ""
        pdfs_encontrados = 0

        async for m in ch_manuales.history(limit=50):
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
                    except Exception:
                        await canal_respuesta.send(f"⚠️ Error procesando **{att.filename}** (Corrupto).")

        if texto_consolidado.strip():
            with open(self.txt_file_path, "w", encoding="utf-8") as f:
                f.write(texto_consolidado)
            
            # Borrar backups anteriores del bot para mantener limpio el canal
            async for m in ch_manuales.history(limit=20):
                if m.author == self.bot.user and m.attachments:
                    await m.delete()

            # Enviar el nuevo Backup
            await ch_manuales.send(
                "📂 **BACKUP DEL CEREBRO ACTUALIZADO**\nEl bot cargará este archivo al instante cada vez que se reinicie.",
                file=discord.File(self.txt_file_path)
            )
            await canal_respuesta.send(f"✅ **Sincronización terminada.** ({pdfs_encontrados} PDFs procesados y asegurados en Backup).")
        else:
            await canal_respuesta.send("⚠️ No se encontró texto válido.")

    async def leer_manuales_txt(self, guild):
        """Descarga el backup directamente de Discord para arrancar al instante."""
        ch_manuales = discord.utils.get(guild.channels, name="manuales")
        if ch_manuales:
            async for m in ch_manuales.history(limit=20):
                for att in m.attachments:
                    if att.filename == "manual_unificado.txt":
                        bytes_txt = await att.read()
                        return bytes_txt.decode('utf-8')
        return "No hay manuales cargados. Ejecuta /sincronizar_manuales."

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
        ch_roster = discord.utils.get(guild.channels, name="roster-global")
        texto_roster = ""
        if ch_roster:
            async for m in ch_roster.history(limit=20):
                if m.content: texto_roster += f"\n{m.content}\n"
        self.cache_roster = texto_roster
        return self.cache_roster

    async def auto_actualizar_roster(self, guild, datos_imagen):
        """Proceso silencioso que actualiza el Roster global editando el mensaje si detecta oficiales nuevos o ascendidos."""
        ch_roster = discord.utils.get(guild.channels, name="roster-global")
        if not ch_roster: return

        # Buscar el mensaje principal del Roster
        roster_msg = None
        async for m in ch_roster.history(limit=10):
            if "ESCALA JERÁRQUICA" in m.content:
                roster_msg = m
                break
        
        if not roster_msg: return

        sys_prompt = f"""
        Eres el administrador de la base de datos policial.
        
        ROSTER ACTUAL DE LA COMISARÍA:
        {roster_msg.content}
        
        NUEVOS DATOS EXTRAÍDOS DE UNA CAPTURA RECIENTE:
        {datos_imagen}
        
        TAREA:
        1. Analiza los nombres y rangos de los NUEVOS DATOS.
        2. Compáralos con la 'LISTA DE OFICIALES ACTIVOS' del ROSTER ACTUAL.
        3. Si un oficial NO ESTÁ en la lista, agrégalo al final de los oficiales activos.
        4. Si un oficial YA ESTÁ pero en la captura aparece con un rango SUPERIOR, actualízalo. (Usa los números de la escala jerárquica para saber qué rango es superior). No bajes de rango a nadie.
        5. DEVUELVE ÚNICAMENTE EL TEXTO COMPLETO DEL ROSTER ACTUALIZADO (Escala y Lista). Cero comentarios, sin bloques de código ```. Debe ser texto crudo listo para copiar.
        """
        
        try:
            res = await self.groq.chat.completions.create(
                messages=[{"role": "system", "content": sys_prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.0
            )
            nuevo_roster = res.choices[0].message.content.replace("```text", "").replace("```", "").strip()
            
            # Si el mensaje es del bot, lo edita. Si lo enviaste tú, lo borra y el bot asume el control del Roster.
            if roster_msg.author == self.bot.user:
                await roster_msg.edit(content=nuevo_roster)
            else:
                await roster_msg.delete()
                await ch_roster.send(nuevo_roster)
                
            self.cache_roster = nuevo_roster
        except Exception:
            pass

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
            ("manuales", "📚 **CANAL DE MANUALES GLOBALES**\nSube los PDFs. El bot hará un Backup aquí mismo."),
            ("plantillas", "📌 **CANAL DE PLANTILLAS GLOBALES**\nPega aquí los formatos vacíos."),
            ("roster-global", "👥 **BASE DE DATOS DE LA COMISARÍA**\nPega aquí la jerarquía y lista de oficiales inicial. El bot la actualizará sola con el uso.")
        ]:
            ch = discord.utils.get(g.channels, name=ch_name)
            if not ch:
                ch = await g.create_text_channel(ch_name, category=cat)
                await ch.send(desc)

        await interaction.followup.send("✅ Canales maestros creados y vinculados.")

    @app_commands.command(name="sincronizar_manuales", description="Fuerza la transcripción de PDFs y crea el Backup.")
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

        await ch_n.send(f"👋 **ESPACIO DE TRABAJO**\n{u.mention} Sube fotos o pide reportes aquí.")
        await interaction.followup.send(f"✅ Canales listos: {cat.jump_url}")

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot: return

        if msg.channel.name == "manuales" and msg.attachments:
            # Solo auto-sincroniza si suben un PDF, ignorando los backups del bot
            if any(a.filename.endswith('.pdf') for a in msg.attachments):
                await self.sync_manuales(msg.guild, msg.channel)
            return
            
        if msg.channel.name == "plantillas" or msg.channel.name == "roster-global":
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
                                                {"type": "text", "text": "Transcribe todos los nombres y rangos exactamente como aparecen en esta imagen. Detalla todo el texto encontrado."},
                                                {"type": "image_url", "image_url": {"url": att.url}}
                                            ]
                                        }],
                                        model="llama-3.2-11b-vision-preview"
                                    )
                                    imagen_analisis += f"\n[Datos de imagen]:\n{vision_res.choices[0].message.content}\n"
                                    tiene_nombres = True
                                except Exception:
                                    pass

                    # LANZAR ACTUALIZACIÓN DE ROSTER EN SEGUNDO PLANO (Sin detener la respuesta al usuario)
                    if tiene_nombres:
                        asyncio.create_task(self.auto_actualizar_roster(msg.guild, imagen_analisis))

                    manuales_texto = await self.leer_manuales_txt(msg.guild)
                    plantillas_texto = await self.cargar_plantillas_globales(msg.guild)
                    roster_texto = await self.cargar_roster_global(msg.guild)
                    historial_chat = "\n".join([f"{m.author.display_name}: {m.content}" async for m in msg.channel.history(limit=8) if not m.author.bot])

                    frases_informe = ["redacta el informe", "genera el informe", "redáctame un informe", "redacta un informe"]
                    es_peticion_informe = any(frase in msg.content.lower() for frase in frases_informe)

                    sys_prompt = f"""
                    Eres un sistema de procesamiento de datos policiales estricto.
                    
                    MANUALES Y CÓDIGOS: {manuales_texto[:4000]}
                    PLANTILLAS OFICIALES: {plantillas_texto[:3000]}
                    BASE DE DATOS (ROSTER): {roster_texto[:3000]}
                    DATOS DE IMÁGENES RECIENTES: {imagen_analisis}
                    CONTEXTO RECIENTE: {historial_chat}
                    
                    REGLAS ABSOLUTAS:
                    1. ORDENAMIENTO: Si te envían una lista o imagen y piden ordenarla, cruza los datos con la BASE DE DATOS (ROSTER) para ordenarlos estrictamente de MAYOR a MENOR rango, incluyendo el rango al lado.
                    2. REDACCIÓN ESTRICTA: Si piden "redacta el informe", rellena la plantilla correspondiente con los datos recabados. Devuelve SOLO la plantilla lista.
                    3. RESPUESTAS CORTAS: Si es una duda rápida, copy o código, devuelve solo el texto útil sin palabras de relleno (nada de "Aquí tienes", etc.).
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
