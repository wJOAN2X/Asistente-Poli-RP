import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
from google import genai
from google.genai import types

class FichasSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        
        # El Prompt Maestro que definimos anteriormente
        self.SYSTEM_INSTRUCTION = """
        Actúa como un evaluador estricto y objetivo del equipo de "Fichas e Invitaciones" para un servidor de Roleplay. Tu objetivo es analizar exhaustivamente las fichas de personaje (PJ) enviadas por los usuarios y determinar si son aprobadas o denegadas basándote en una normativa específica. No debes tener favoritismos y debes exigir el mismo nivel de detalle a todas las fichas.

        NORMATIVA DE EVALUACIÓN (CRITERIOS OBLIGATORIOS):
        1. Nombre y Apellidos: Deben ser reales, acordes al país de origen y coherentes con los padres. Rechaza nombres de famosos, personajes ficticios o nombres troll.
        2. Fecha de nacimiento y Edad: La edad debe calcularse correctamente respecto a la fecha. El PJ debe ser estrictamente mayor de 18 años.
        3. Ciudad y país de nacimiento: Debe ser un lugar real y coherente con la historia. Regla estricta: Si dice "Los Ángeles", debes rechazarlo e indicar que Los Santos se basa en Los Ángeles.
        4. Lazos familiares: Debe incluir Nombres + Parentesco + Tipo de relación.
        5. Etnia: Solo puede haber UNA opción (Caucásico, latino, afrodescendiente, asiático, gitano, árabe).
        6. Breve descripción del personaje (Mínimo 5 líneas): Físico (detalles específicos) y Psicología (Carácter, personalidad). Miedos y Gustos justificados. No gustos enfocados al PVP (matar, disparar).
        7. ¿Por qué viaja a Los Santos?: Justificado por su pasado. Rechaza frases vacías como "para empezar de nuevo".
        8. Antecedentes: Especificar delito/tiempo o enfermedad. Si no los tiene, debe decir explícitamente "N/A".
        9. Historia del personaje (Mínimo 8 líneas completas): Estructura clara (pasado, presente y futuro).

        FORMATO DE RESPUESTA:

        Si CUMPLE todo:
        ✅ **FICHA APROBADA**
        La ficha cumple con la normativa. 
        *Recordatorio para el Staff:* 
        1. Enviar información al form de registro ⁠📑┊𝐃𝐨𝐜𝐮𝐦𝐞𝐧𝐭𝐨𝐬. 
        2. Quitar roles: Ficha rechazada / Formulario aceptado / Acceso a WL. 
        3. Añadir roles: Ciudadano / Ficha aceptada V2. 
        4. Cerrar ticket (Guardar y Eliminar).

        Si NO CUMPLE (Usa estrictamente esta plantilla, deja solo los bullet points fallidos):
        ## ❌ FICHA DENEGADA ❌
        📄 Tu ficha no ha sido aprobada por el momento.

        Por favor, corrige lo siguiente:
        > - **[Nombre del apartado fallido]:** [Explicación clara de por qué falló].

        🔁 _Puedes editar sobre lo que escribiste y si no te alcanza, debes enviarla de nuevo **completa** en varios mensajes de ser necesario. Recuerda en todo momento seguir la plantilla establecida._

        ¡Ánimo! Estamos aquí para ayudarte a formar parte de New Day.

        :newdayv2: **Tienes 12 horas para corregir los fallos, pasado ese tiempo se cerrará el ticket por inactividad. Sin embargo, siempre puedes volver a abrir otro ticket cuando ya tengas lista tu ficha.** :newdayv2:
        @
        """

    async def enviar_texto_largo(self, canal, texto, msg_original=None):
        """Divide el texto si supera el límite de caracteres de Discord."""
        pedazos = [texto[i:i+1900] for i in range(0, len(texto), 1900)]
        for idx, pedazo in enumerate(pedazos):
            if idx == 0 and msg_original:
                await msg_original.reply(pedazo)
            else:
                await canal.send(pedazo)

    @app_commands.command(name="setup_fichas", description="[ADMIN] Crea el canal dedicado para la corrección de fichas de PJ.")
    @app_commands.default_permissions(administrator=True)
    async def setup_fichas(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        g = interaction.guild

        cat = discord.utils.get(g.categories, name="📋 ADMINISTRACIÓN")
        if not cat: 
            cat = await g.create_category("📋 ADMINISTRACIÓN")

        canal_nombre = "revision-fichas"
        ch = discord.utils.get(g.channels, name=canal_nombre)
        
        if not ch:
            ch = await g.create_text_channel(canal_nombre, category=cat)
            instrucciones = (
                "🤖 **MÓDULO DE REVISIÓN AUTOMÁTICA ACTIVO**\n"
                "Todo mensaje enviado en este canal será tratado como una ficha de personaje.\n"
                "Pega la ficha completa y la IA te responderá con la plantilla de aprobación o rechazo."
            )
            await ch.send(instrucciones)
            await interaction.followup.send(f"✅ Canal {ch.mention} creado con éxito.")
        else:
            await interaction.followup.send(f"⚠️ El canal {ch.mention} ya existe.")

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        # Ignorar bots
        if msg.author.bot: 
            return

        # Solo actuar si el mensaje se envía en el canal correcto
        if msg.channel.name == "revision-fichas":
            await msg.add_reaction("👀") # Indicador visual de que está leyendo
            
            async with msg.channel.typing():
                try:
                    # Configuración estricta (temperature=0.0) para que no invente reglas y se ciña a la plantilla
                    response = self.client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=msg.content,
                        config=types.GenerateContentConfig(
                            system_instruction=self.SYSTEM_INSTRUCTION,
                            temperature=0.0 
                        )
                    )

                    respuesta = response.text

                    # Cambiar la reacción al terminar
                    await msg.remove_reaction("👀", self.bot.user)
                    
                    if "FICHA APROBADA" in respuesta:
                        await msg.add_reaction("✅")
                    else:
                        await msg.add_reaction("❌")

                    # Enviar la respuesta analizada
                    await self.enviar_texto_largo(msg.channel, respuesta, msg_original=msg)

                except Exception as e:
                    await msg.remove_reaction("👀", self.bot.user)
                    await msg.add_reaction("⚠️")
                    await msg.reply(f"⚠️ **Error en el sistema de análisis:** `{e}`")

async def setup(bot):
    await bot.add_cog(FichasSystem(bot))
