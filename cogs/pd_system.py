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

    async def actualizar_archivo_manuales(self, guild):
        ch_manuales = discord.utils.get(guild.channels, name="manuales")
        if not ch_manuales: return
        
        texto_consolidado = ""
        async for m in ch_manuales.history(limit=25):
            if m.content: texto_consolidado += f"\n{m.content}\n"
            for att in m.attachments:
                if att.filename.endswith('.pdf'):
                    try:
                        pdf = PdfReader(io.BytesIO(await att.read()))
                        for page in pdf.pages:
                            try:
                                text = page.extract_text()
                                if text: texto_consolidado += text + "\n"
                            except Exception:
                                pass # Ignora páginas corruptas
                    except Exception:
                        pass # Ignora PDFs completamente rotos
        
        if texto_consolidado.strip():
            with open(self.txt_file_path, "w", encoding="utf-8") as f:
                f.write(texto_consolidado)

    async def leer_manuales_txt(self, guild):
        if not os.path.exists(self.txt_file_path):
            await self.actualizar_archivo_manuales(guild)
        
        if os.path.exists(self.txt_file_path):
            with open(self.txt_file_path, "r", encoding="utf-8") as f:
                return f.read()
        return "No hay manuales cargados."

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

    async def enviar_texto_largo(self, canal, texto, msg_original=None):
        pedazos = [texto[i:i+1900] for i in range(0, len(texto), 1900)]
        for idx, pedazo in enumerate(pedazos):
            if idx == 0 and msg_original:
                await msg_original.reply(pedazo)
            else:
                await canal.send(pedazo)

    @app_commands.command(name="alta_personaje", description="Crea tus canales de trabajo y ajusta tu nombre.")
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

        nuevo_apodo = f"[{rango}] {nombre_personaje}"
        aviso_apodo = ""
        try:
            await u.edit(nick=nuevo_apodo[:32])
        except discord.Forbidden:
            aviso_apodo = "\n*(No pude cambiar tu apodo porque eres el dueño del servidor o tienes un rol mayor al mío).* "

        await ch_e.send(f"📌 **BASE DE APRENDIZAJE**\n{u.mention} Pega aquí tus informes pasados para que la IA aprenda tu estilo.")
        await ch_n.send(f"👋 **ESPACIO DE TRABAJO**\n{u.mention} Pide internas, haz preguntas sobre el manual, sube imágenes/audios o escribe 'redacta el informe'.")
        
        await interaction.followup.send(f"✅ Canales listos: {cat.jump_url}{aviso_apodo}")

    @app_commands.command(name="actualizar_rango", description="Actualiza tu rango por un ascenso (renombra tus canales, rol y apodo).")
    async def actualizar_rango(self, interaction: discord.Interaction, nuevo_rango: str):
        await interaction.response.defer(ephemeral=True)
        cat = interaction.channel.category
        u = interaction.user

        if not cat:
            return await interaction.followup.send("❌ Usa este comando dentro de tu categoría de trabajo.")
        
        try:
            partes = cat.name.split(" | ", 1)
            faccion = partes[0]
            nombre_personaje = partes[1].split(" - ", 1)[1]
        except Exception:
            return await interaction.followup.send("❌ El nombre de tu categoría fue modificado manualmente o está corrupto. No puedo automatizar el ascenso.")

        nuevo_nombre_completo = f"{faccion} | {nuevo_rango} - {nombre_personaje}"
        nuevo_apodo = f"[{nuevo_rango}] {nombre_personaje}"

        rol_existente = discord.utils.get(u.roles, name=cat.name)
        if rol_existente:
            await rol_existente.edit(name=nuevo_nombre_completo)

        await cat.edit(name=nuevo_nombre_completo)

        aviso_apodo = ""
        try:
            await u.edit(nick=nuevo_apodo[:32])
        except discord.Forbidden:
            aviso_apodo = "\n*(Tus canales se actualizaron, pero no pude cambiar tu apodo por falta de permisos/jerarquía).* "

        await interaction.followup.send(f"🎖️ **¡Ascenso procesado!** Ahora eres **{nuevo_rango}**.\nCanales y roles actualizados correctamente.{aviso_apodo}")

    @app_commands.command(name="borrar_historial", description="Limpia la caché y memoria de tus canales.")
    async def borrar_historial(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cat = interaction.channel.category
        if not cat:
            return await interaction.followup.send("❌ Debes usar este comando dentro de tu categoría de trabajo.")
        
        ch_e = discord.utils.get(cat.channels, name="📚-ejemplos-pasados")
        ch_n = discord.utils.get(cat.channels, name="💭-registro-y-dudas")
        
        if ch_e: 
            if ch_e.id in self.cache_ejemplos: del self.cache_ejemplos[ch_e.id]
            await ch_e.purge(limit=50)
            await ch_e.send("🧹 **Canal de ejemplos limpiado.**")
            
        if ch_n: 
            await ch_n.purge(limit=50)
            await ch_n.send("🧹 **Memoria a corto plazo borrada.**")
            
        await interaction.followup.send("✅ Purgado completado con éxito.")

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot: return

        if msg.channel.name == "manuales":
            if os.path.exists(self.txt_file_path):
                os.remove(self.txt_file_path)
            await self.actualizar_archivo_manuales(msg.guild)
            await msg.add_reaction("✅")
            return
            
        if msg.channel.name == "📚-ejemplos-pasados":
            if msg.channel.id in self.cache_ejemplos:
                del self.cache_ejemplos[msg.channel.id]
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
                                                {"type": "text", "text": "Extrae detalladamente todo el texto, tablas, nombres, rangos o información relevante que aparezca en esta imagen. Si hay listas, mantenlas estructuradas."},
                                                {"type": "image_url", "image_url": {"url": att.url}}
                                            ]
                                        }],
                                        model="llama-3.2-11b-vision-preview"
                                    )
                                    imagen_analisis += f"\n[Datos extraídos de la imagen adjunta]:\n{vision_res.choices[0].message.content}\n"
                                except Exception:
                                    pass

                    manuales_texto = await self.leer_manuales_txt(msg.guild)

                    cat = msg.channel.category
                    textos_ejemplos = ""
                    if cat:
                        ch_e = discord.utils.get(cat.channels, name="📚-ejemplos-pasados")
                        if ch_e:
                            textos_ejemplos = await self.cargar_ejemplos_usuario(ch_e)

                    historial_chat = "\n".join([f"{m.author.display_name}: {m.content}" async for m in msg.channel.history(limit=10) if not m.author.bot])

                    sys_prompt = f"""
                    Eres el asistente operativo y de redacción policial de este servidor de Roleplay.
                    
                    RECURSOS OFICIALES (Leyes y Manuales):
                    {manuales_texto[:6000]}
                    
                    DATOS DE IMÁGENES RECIENTES:
                    {imagen_analisis}
                    
                    EJEMPLOS DE ESTILO Y FORMATO DEL OFICIAL:
                    {textos_ejemplos[:3000]}
                    
                    CONTEXTO:
                    {historial_chat}
                    
                    INSTRUCCIONES CLAVE:
                    - Sé extremadamente directo y conciso. No uses relleno ni frases introductorias.
                    - Si el usuario te pide extraer datos de una imagen (ej. nombres para un reporte), dáselos en el formato exacto que pide (ej. una lista limpia y ordenada en el mismo chat).
                    - Solo debes aplicar el estilo de los ejemplos y extenderte si el usuario pide la redacción final de un informe.
                    """

                    res = await self.groq.chat.completions.create(
                        messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": msg.content if msg.content else "Procesa la imagen adjunta."}],
                        model="llama-3.3-70b-versatile",
                        temperature=0.2
                    )

                    respuesta = res.choices[0].message.content

                    # DISPARADOR ESTRICTO: Solo enviará al canal de informes si usas estas frases exactas.
                    frases_informe = ["redacta el informe", "genera el informe", "redáctame un informe", "redacta un informe"]
                    es_peticion_informe = any(frase in msg.content.lower() for frase in frases_informe)

                    if es_peticion_informe:
                        if cat:
                            ch_i = discord.utils.get(cat.channels, name="📋-informes")
                            if ch_i:
                                texto_informe = f"📋 **INFORME GENERADO:**\n\n{respuesta}"
                                await self.enviar_texto_largo(ch_i, texto_informe)
                                await msg.remove_reaction("👀", self.bot.user)
                                await msg.add_reaction("✅")
                                return await msg.reply("✅ Informe redactado y enviado a tu canal de informes.")

                    await msg.remove_reaction("👀", self.bot.user)
                    await msg.add_reaction("✅")
                    await self.enviar_texto_largo(msg.channel, respuesta, msg_original=msg)

                except Exception as e:
                    await msg.remove_reaction("👀", self.bot.user)
                    await msg.add_reaction("❌")
                    await msg.reply(f"⚠️ **Error procesando la solicitud:**\n`{e}`")

async def setup(bot):
    await bot.add_cog(RPSystem(bot))
