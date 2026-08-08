import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import os
import io
from PyPDF2 import PdfReader
from groq import AsyncGroq

class PDSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "pd_database.db"
        self.groq_client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

    async def cog_load(self):
        # Crear DB SQLITE local para el PD
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''CREATE TABLE IF NOT EXISTS oficiales (
                                discord_id TEXT PRIMARY KEY, rango TEXT, categoria_id TEXT,
                                ch_plantillas TEXT, ch_informes TEXT, ch_notas TEXT)''')
            await db.execute('''CREATE TABLE IF NOT EXISTS manuales (
                                nombre TEXT PRIMARY KEY, contenido TEXT)''')
            await db.execute('''CREATE TABLE IF NOT EXISTS config (
                                clave TEXT PRIMARY KEY, valor TEXT)''')
            await db.commit()

    async def get_manual_channel(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT valor FROM config WHERE clave='canal_manuales'")
            row = await cursor.fetchone()
            return int(row[0]) if row else None

    # COMANDOS
    @app_commands.command(name="pd_setup_manuales", description="Define el canal actual para subir PDFs y actualizar la DB.")
    @app_commands.default_permissions(administrator=True)
    async def pd_setup(self, interaction: discord.Interaction):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT OR REPLACE INTO config (clave, valor) VALUES (?, ?)", ("canal_manuales", str(interaction.channel_id)))
            await db.commit()
        await interaction.response.send_message("✅ Canal configurado. Sube PDFs aquí para actualizar la base de datos.", ephemeral=True)

    @app_commands.command(name="pd_alta", description="Registra a un oficial y crea sus canales de informes.")
    async def pd_alta(self, interaction: discord.Interaction, rango: str):
        await interaction.response.defer(ephemeral=True)
        guild, user = interaction.guild, interaction.user

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT * FROM oficiales WHERE discord_id = ?", (str(user.id),))
            if await cursor.fetchone():
                return await interaction.followup.send("❌ Ya estás registrado.", ephemeral=True)

            ow = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
            }
            cat = await guild.create_category(f"🚓 {rango} - {user.display_name}", overwrites=ow)
            ch_plantillas = await guild.create_text_channel("📝-plantillas", category=cat)
            ch_informes = await guild.create_text_channel("📋-informes", category=cat)
            ch_notas = await guild.create_text_channel("💭-notas-y-dudas", category=cat)

            await ch_notas.send(f"Bienvenido {user.mention}. Manda aquí tus apuntes, capturas de pantalla o audios. Pide que genere un informe y lo haré en tu canal de informes.")

            await db.execute("INSERT INTO oficiales VALUES (?, ?, ?, ?, ?, ?)", 
                             (str(user.id), rango, str(cat.id), str(ch_plantillas.id), str(ch_informes.id), str(ch_notas.id)))
            await db.commit()
        await interaction.followup.send(f"✅ Estructura creada: {cat.jump_url}", ephemeral=True)

    # LÓGICA DE IA AL RECIBIR MENSAJES
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot: return

        manual_ch = await self.get_manual_channel()

        # 1. ACTUALIZAR BASE DE DATOS RAG (Leer PDF)
        if message.channel.id == manual_ch and message.attachments:
            for att in message.attachments:
                if att.filename.endswith('.pdf'):
                    await message.add_reaction("⏳")
                    pdf_bytes = await att.read()
                    reader = PdfReader(io.BytesIO(pdf_bytes))
                    texto = "\n".join([p.extract_text() for p in reader.pages if p.extract_text()])
                    
                    async with aiosqlite.connect(self.db_path) as db:
                        await db.execute("INSERT OR REPLACE INTO manuales (nombre, contenido) VALUES (?, ?)", (att.filename, texto))
                        await db.commit()
                    await message.add_reaction("✅")
                    await message.reply(f"📖 Manual `{att.filename}` actualizado en el cerebro de Groq.")
            return

        # 2. VERIFICAR SI ESTÁ EN CANAL PRIVADO
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT * FROM oficiales WHERE ch_notas = ?", (str(message.channel.id),))
            oficial = await cursor.fetchone()

        if oficial:
            is_notas = True
            
            # Recuperar manuales
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("SELECT contenido FROM manuales")
                manuales = "\n".join([row[0] for row in await cursor.fetchall()])

            # A. LECTURA DE AUDIO / BRIEFING (Whisper)
            if message.attachments and any(a.filename.endswith(('.mp3', '.m4a', '.ogg', '.wav')) for a in message.attachments):
                async with message.channel.typing():
                    att = message.attachments[0]
                    audio_bytes = await att.read()
                    
                    # Groq Whisper
                    transcripcion = await self.groq_client.audio.transcriptions.create(
                        file=(att.filename, audio_bytes),
                        model="whisper-large-v3",
                        response_format="text"
                    )
                    await message.reply(f"🎙️ **Transcripción del Briefing:**\n{transcripcion}\n\n*Pídemelo si quieres que haga el informe en base a esto.*")
                    return

            # B. LECTURA DE IMAGEN / CAPTURA (Llama-Vision)
            elif message.attachments and any(a.filename.endswith(('.png', '.jpg', '.jpeg')) for a in message.attachments):
                async with message.channel.typing():
                    img_url = message.attachments[0].url
                    respuesta = await self.groq_client.chat.completions.create(
                        messages=[{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Analiza esta imagen policial. ¿Hay cambios de rango, incautaciones o datos para un informe?"},
                                {"type": "image_url", "image_url": {"url": img_url}}
                            ]
                        }],
                        model="llama-3.2-11b-vision-preview",
                    )
                    await message.reply(f"👁️ **Análisis Visual:**\n{respuesta.choices[0].message.content}")
                    return

            # C. PETICIÓN DE INFORME O DUDA (Texto)
            if "informe" in message.content.lower() or "duda" in message.content.lower():
                async with message.channel.typing():
                    historial = [m async for m in message.channel.history(limit=15) if not m.author.bot]
                    contexto_notas = "\n".join([m.content for m in historial])

                    sys_prompt = f"""Eres IA policial. Usa estos manuales: {manuales[:4000]}
                    Contexto de chat del oficial: {contexto_notas}
                    Si pide un informe, hazlo detallado según el manual. Si es una duda, respóndela."""
                    
                    respuesta = await self.groq_client.chat.completions.create(
                        messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": message.content}],
                        model="llama3-70b-8192"
                    )
                    
                    if "informe" in message.content.lower():
                        ch_informes = self.bot.get_channel(int(oficial[4]))
                        await ch_informes.send(f"📋 **NUEVO INFORME GENERADO:**\n\n{respuesta.choices[0].message.content}")
                        await message.reply("✅ Informe redactado y enviado a tu canal de informes.")
                    else:
                        await message.reply(respuesta.choices[0].message.content)

async def setup(bot):
    await bot.add_cog(PDSystem(bot))
