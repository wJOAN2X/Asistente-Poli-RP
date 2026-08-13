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
        
        self.SYSTEM_INSTRUCTION = """
        Actúa como un evaluador estricto y objetivo del equipo de "Fichas e Invitaciones" para un servidor de Roleplay. Tu objetivo es analizar exhaustivamente las fichas de personaje (PJ) enviadas por los usuarios y determinar si son aprobadas o denegadas basándote en una normativa específica. No debes tener favoritismos y debes exigir el mismo nivel de detalle a todas las fichas.

        NORMATIVA DE EVALUACIÓN (CRITERIOS OBLIGATORIOS):
        1. Nombre y Apellidos: Deben ser reales, acordes al país de origen y coherentes con los padres. Rechaza nombres de famosos, personajes ficticios o nombres troll.
        2. Fecha de nacimiento y Edad: La edad debe calcularse correctamente respecto a la fecha. El PJ debe ser estrictamente mayor de 18 años.
        3. Ciudad y país de nacimiento: Debe ser un lugar real y coherente con la historia. Regla estricta: Si dice "Los Ángeles", debes rechazarlo e indicar que Los Santos se basa en Los Ángeles, por lo que deberá cambiarlo por Los Santos u otra ciudad.
        4. Lazos familiares: Debe incluir Nombres + Parentesco + Tipo de relación (cómo se llevan, nivel de cercanía).
        5. Etnia: Solo puede haber UNA opción (Caucásico, latino, afrodescendiente, asiático, gitano, árabe). Si dice España es caucásico, si dice América hispanohablante es latino.
        6. Breve descripción del personaje (Mínimo 5 líneas): Físico (detalles específicos de rostro, altura, tatuajes) y Psicología (Carácter, personalidad, forma de actuar). Miedos y Gustos: Deben explicar el por qué. No se aceptan gustos incoherentes o pvperos como disparar o matar.
        7. ¿Por qué viaja a Los Santos?: Justificado por su pasado. Rechaza frases vacías como "para empezar de nuevo" sin un contexto coherente.
        8. Antecedentes (Penales y médicos): Especificar delito/tiempo o enfermedad. Si no los tiene, debe decir explícitamente "N/A" o "Ninguno".
        9. Historia del personaje (Mínimo 8 líneas completas): Estructura clara diferenciando pasado (infancia, educación), presente y futuro (ambiciones). Lo escrito arriba debe tener sentido aquí.

        FORMATO DE RESPUESTA:

        ====== SI LA FICHA CUMPLE ABSOLUTAMENTE TODO ======
        Responde con el texto de aprobación y, SOLO SI tiene antecedentes médicos o penales reales (distintos a N/A), genera las plantillas correspondientes rellenadas con sus datos. Utiliza el "ID Discord del Usuario" proporcionado por el sistema.

        ✅ **FICHA APROBADA**
        La ficha cumple con la normativa. 
        *Recordatorio para el Staff:* 
        1. Enviar información al form de registro ⁠📑┊𝐃𝐨𝐜𝐮𝐦𝐞𝐧𝐭𝐨𝐬. 
        2. Quitar roles: Ficha rechazada / Formulario aceptado / Acceso a WL. 
        3. Añadir roles: Ciudadano / Ficha aceptada V2. 
        4. Cerrar ticket (Guardar y Eliminar).

        [SI TIENE ANTECEDENTES MÉDICOS VÁLIDOS, AGREGA ESTO]:
        **🏥 Plantilla para Antecedentes Médicos:**
        ```text
        ID Discord: [ID Discord proporcionado por el sistema]
        Nombre y Apellido: [Nombre del PJ]
        Fecha de nacimiento y edad: [Fecha] / [Edad]
        Antecedentes médicos: [Detalle exacto de sus antecedentes médicos]
        ```

        [SI TIENE ANTECEDENTES PENALES VÁLIDOS, AGREGA ESTO]:
        **🚨 Plantilla para Antecedentes Penales:**
        ```text
        ID Discord: [ID Discord proporcionado por el sistema]
        Nombre y apellidos IC: [Nombre del PJ]
        Fecha de nacimiento y edad: [Fecha] / [Edad]
        Antecedentes penales: [Detalle exacto de sus antecedentes penales y tiempo en cárcel]
        ```
        (NO generes las plantillas de antecedentes si el usuario puso "N/A" o no tiene).

        ====== SI LA FICHA NO CUMPLE (DENEGADA) ======
        Usa estrictamente esta plantilla, deja solo los bullet points de los apartados fallidos y explica el motivo, elimina los bullet points que sí estén bien:

        ## ❌ FICHA DENEGADA ❌
        📄 Tu ficha no ha sido aprobada por el momento.

        Por favor, corrige lo siguiente:
        > - **[Nombre del apartado fallido]:** [Explicación clara de por qué falló según la normativa].

        🔁 _Puedes editar sobre lo que escribiste y si no te alcanza, debes enviarla de nuevo **completa** en varios mensajes de ser necesario. Recuerda en todo momento seguir la plantilla establecida._

        ¡Ánimo! Estamos aquí para ayudarte a formar parte de New Day.

        :newdayv2: **Tienes 12 horas para corregir los fallos, pasado ese tiempo se cerrará el ticket por inactividad. Sin embargo, siempre puedes volver a abrir otro ticket cuando ya tengas lista tu ficha.** :newdayv2:
        @
        """

    async def enviar_texto_largo(self, canal, texto, msg_original=None):
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
                "Puedes pegar la ficha completa directamente o **adjuntar un archivo `.txt`** si tu ficha es demasiado larga."
            )
            await ch.send(instrucciones)
            await interaction.followup.send(f"✅ Canal {ch.mention} creado con éxito.")
        else:
            await interaction.followup.send(f"⚠️ El canal {ch.mention} ya existe.")

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot: 
            return

        if msg.channel.name == "revision-fichas":
            await msg.add_reaction("👀")
            
            async with msg.channel.typing():
                try:
                    # Le inyectamos a la IA el ID real de Discord del usuario que envió el mensaje
                    contenido_ficha = f"[DATOS DEL SISTEMA]\nID Discord del Usuario: {msg.author.id}\n\n[CONTENIDO DE LA FICHA]\n{msg.content}"

                    if msg.attachments:
                        for adjunto in msg.attachments:
                            if adjunto.filename.endswith('.txt'):
                                try:
                                    archivo_bytes = await adjunto.read()
                                    texto_extraido = archivo_bytes.decode('utf-8', errors='ignore')
                                    contenido_ficha += f"\n\n[CONTENIDO DEL ARCHIVO TXT]\n{texto_extraido}"
                                except Exception as e:
                                    await msg.reply(f"⚠️ No pude leer el archivo {adjunto.filename}: {e}")

                    # Verificamos que haya más texto que solo el ID que inyectamos
                    if len(msg.content.strip()) == 0 and not msg.attachments:
                        await msg.remove_reaction("👀", self.bot.user)
                        return

                    response = self.client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=contenido_ficha,
                        config=types.GenerateContentConfig(
                            system_instruction=self.SYSTEM_INSTRUCTION,
                            temperature=0.0 
                        )
                    )

                    respuesta = response.text

                    await msg.remove_reaction("👀", self.bot.user)
                    
                    if "FICHA APROBADA" in respuesta:
                        await msg.add_reaction("✅")
                    else:
                        await msg.add_reaction("❌")

                    await self.enviar_texto_largo(msg.channel, respuesta, msg_original=msg)

                except Exception as e:
                    await msg.remove_reaction("👀", self.bot.user)
                    await msg.add_reaction("⚠️")
                    await msg.reply(f"⚠️ **Error en el sistema de análisis:** `{e}`")

async def setup(bot):
    await bot.add_cog(FichasSystem(bot))
