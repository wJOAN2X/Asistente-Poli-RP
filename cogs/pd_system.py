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
        
        # MEMORIA RAM / CACHÉ INTELIGENTE (Para responder rápido sin depender de bases de datos lentas)
        self.cache_manuales = ""
        self.cache_ejemplos = {} # Guarda los ejemplos por cada usuario en memoria

    async def cargar_manuales_globales(self, guild):
        """Lee el canal #manuales una vez y lo guarda en caché para velocidad máxima."""
        if self.cache_manuales: return self.cache_manuales
        
        texto_global = ""
        ch_manuales = discord.utils.get(guild.channels, name="manuales")
        if ch_manuales:
            async for m in ch_manuales.history(limit=15):
                if m.content: texto_global += f"\n{m.content}\n"
                for att in m.attachments:
                    if att.filename.endswith('.pdf'):
                        try:
                            pdf = PdfReader(io.BytesIO(await att.read()))
                            texto_global += "\n".join([p.extract_text() for p in pdf.pages if p.extract_text()])
                        except Exception:
                            pass
        self.cache_manuales = texto_global
        return self.cache_manuales

    async def cargar_ejemplos_usuario(self, ch_ejemplos):
        """Lee los ejemplos de estilo del usuario y los almacena en caché."""
        ch_id = ch_ejemplos.id
        if ch_id in self.cache_ejemplos:
            return self.cache_ejemplos[ch_id]

        textos_ejemplos = ""
        async for m in ch_ejemplos.history(limit=15):
            if not m.author.bot and m.content:
                textos_ejemplos += f"\n--- EJEMPLO DE INFORME ---\n{m.content}\n"
        
        self.cache_ejemplos[ch_id] = textos_ejemplos
        return self.cache_ejemplos[ch_id]

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

        await ch_e.send(f"📌 **BASE DE APRENDIZAJE**\n{u.mention} Pega aquí tus informes pasados. La IA los leerá para aprender tu estructura y estilo.")
        await ch_n.send(f"👋 **ESPACIO DE TRABAJO**\n{u.mention} Escribe tus notas, pide internas o escribe 'redacta el informe' para procesarlo al instante.")
        
        await interaction.followup.send(f"✅ Canales listos: {cat.jump_url}")

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
            await ch_e.send("🧹 **Canal de ejemplos limpiado y caché reseteada.**")
            
        if ch_n: 
            await ch_n.purge(limit=50)
            await ch_n.send("🧹 **Memoria a corto plazo borrada.**")
            
        await interaction.followup.send("✅ Purgado completado con éxito.")

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot: return

        # Si actualizan manuales o ejemplos en vivo, reseteamos la caché al instante para que aprendan lo nuevo
        if msg.channel.name == "manuales":
            self.cache_manuales = ""
            await msg.add_reaction("✅")
            return
            
        if msg.channel.name == "📚-ejemplos-pasados":
            if msg.channel.id in self.cache_ejemplos:
                del self.cache_ejemplos[msg.channel.id] # Borra caché para obligar a releer lo nuevo que pegó
            await msg.add_reaction("✅")
            return

        # ZONA DE TRABAJO EN EL CANAL DE DUDAS Y REGISTRO
        if msg.channel.name == "💭-registro-y-dudas":
            await msg.add_reaction("👀") # Confirmación visual inmediata de lectura
            
            async with msg.channel.typing():
                try:
                    # 1. Cargar Manuales Globales en Velocidad Luz
                    manuales_texto = await self.cargar_manuales_globales(msg.guild)

                    # 2. Cargar Ejemplos Personales del Usuario en Caché
                    cat = msg.channel.category
                    textos_ejemplos = ""
                    if cat:
                        ch_e = discord.utils.get(cat.channels, name="📚-ejemplos-pasados")
                        if ch_e:
                            textos_ejemplos = await self.cargar_ejemplos_usuario(ch_e)

                    # 3. Historial reciente del chat actual
                    historial_chat = "\n".join([f"{m.author.display_name}: {m.content}" async for m in msg.channel.history(limit=10) if not m.author.bot])

                    # Prompt optimizado para velocidad y precisión total
                    sys_prompt = f"""
                    Eres el asistente operativo y de redacción policial de este servidor de Roleplay.
                    
                    RECURSOS OFICIALES (Leyes y Manuales):
                    {manuales_texto[:6000]}
                    
                    EJEMPLOS DE ESTILO Y FORMATO DEL OFICIAL:
                    {textos_ejemplos[:4000]}
                    
                    INSTRUCCIONES CLAVE:
                    - Si el usuario pide una interna, copy o procedimiento del manual, da el texto exacto, claro y profesional.
                    - Si el usuario pide redactar un informe, toma los datos recientes del chat y ajústalos estrictamente al formato y estructura que muestran los EJEMPLOS DE ESTILO.
                    - Responde directo al grano, sin rodeos ni saludos innecesarios.
                    """

                    res = await self.groq.chat.completions.create(
                        messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": msg.content}],
                        model="llama-3.3-70b-versatile",
                        temperature=0.2
                    )

                    respuesta = res.choices[0].message.content

                    # Si es un informe, mandarlo limpio al canal de informes de su categoría
                    if "informe" in msg.content.lower() or "redacta" in msg.content.lower():
                        if cat:
                            ch_i = discord.utils.get(cat.channels, name="📋-informes")
                            if ch_i:
                                await ch_i.send(f"📋 **INFORME GENERADO:**\n\n{respuesta}")
                                await msg.remove_reaction("👀", self.bot.user)
                                await msg.add_reaction("✅")
                                return await msg.reply("✅ Informe redactado y enviado a tu canal de informes.")

                    # Respuesta estándar para internas, copys y dudas
                    await msg.remove_reaction("👀", self.bot.user)
                    await msg.add_reaction("✅")
                    await msg.reply(respuesta)

                except Exception as e:
                    await msg.remove_reaction("👀", self.bot.user)
                    await msg.add_reaction("❌")
                    await msg.reply(f"⚠️ **Error procesando la solicitud:**\n`{e}`")

async def setup(bot):
    await bot.add_cog(RPSystem(bot))
