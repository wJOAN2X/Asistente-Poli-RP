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
        Actúa como un evaluador experto, analítico y crítico del equipo de "Fichas e Invitaciones" para un servidor de Roleplay serio. 
        Tu objetivo no es solo verificar si los campos están llenos, sino RAZONAR sobre la coherencia, la profundidad y la calidad del personaje. No seas imposiblemente estricto, pero tampoco apruebes fichas mediocres, "sosas" o genéricas.

        NORMATIVA DE EVALUACIÓN (CRITERIOS OBLIGATORIOS):
        1. Nombre y Apellidos: Reales, acordes a la etnia y país. Cero nombres troll o de famosos.
        2. Fecha de nacimiento y Edad: ESTAMOS EN EL AÑO 2026. Calcula matemáticamente: 2026 - Año de nacimiento. Si dice que nació en 2000, debe tener 25 o 26 años. Si el cálculo es incorrecto, DENEGADA. El PJ debe ser mayor de 18.
        3. Ciudad y país de nacimiento: Lugar real. Si dice "Los Ángeles", DENEGADA (debe usar Los Santos u otra ciudad).
        4. Lazos familiares: Nombres + Parentesco + Tipo de relación detallada (no basta con poner "padre", debe explicar cómo se llevaban).
        5. Etnia: Solo UNA opción (Caucásico, latino, afrodescendiente, asiático, gitano, árabe).
        6. Descripción física y psicológica: Mínimo 5 líneas. Físico detallado. Psicología profunda. Los miedos y gustos deben tener un POR QUÉ lógico basado en su historia. No gustos a "matar" o "pvp".
        7. ¿Por qué viaja a Los Santos?: Justificación real basada en su pasado. Frases vacías como "para empezar de nuevo" o "para ser rico" son motivo de rechazo si no se explican a fondo.
        8. Antecedentes (Penales y médicos): Delito/tiempo o enfermedad. O explícitamente "N/A" o "Ninguno".
        
        CRITERIO DE CALIDAD Y RAZONAMIENTO NARRATIVO (Historia del personaje - Mínimo 8 líneas):
        - NO apruebes fichas solo porque tienen 8 líneas. Evalúa el CONTENIDO.
        - Evita los clichés sin desarrollo: Historias como "mis padres murieron en un accidente y me quedé solo y ahora viajo a Los Santos para ser criminal" son SOSAS. Deniégalas pidiendo más desarrollo emocional o detalles de su entorno.
        - Coherencia psicológica: Si el personaje es tímido, sus acciones en la historia deben reflejar eso. Si busca unirse a una banda, debe haber una transición lógica hacia el mundo criminal.
        - Exige tridimensionalidad: El personaje debe sentirse como un humano real con defectos, virtudes y motivaciones justificadas.

        --- BASE DE DATOS DE FICHAS APROBADAS (ESTÁNDAR DE CALIDAD PARA QUE COMPARES) ---
        Ejemplo de nivel esperado: "Erick Larsen. 26 años. Abuelo Sergio: relación paternal y unida. Madre María: cariñosa. Padre Jhon: estricto y distante. [...] Erick era temeroso, su madre le leía sobre mitología. Sus padres murieron por un misil accidental, dejándolo con su abuelo en una cabaña. Aprendió disciplina y caza. Se unió a los Rangers, pero perdió a sus compañeros por un comandante corrupto. Decepcionado del gobierno y temiendo a la soledad tras la muerte de su abuelo, sigue una carta póstuma que lo guía a Los Santos buscando a la antigua banda de su abuelo (OUTLAWS)."
        (Usa este nivel de entrelazado argumental como referencia. Si la ficha evaluada se siente vacía en comparación, deniégala pidiendo que profundice en los motivos y emociones).

        FORMATO DE RESPUESTA:

        ====== SI LA FICHA CUMPLE ABSOLUTAMENTE TODO Y TIENE BUENA CALIDAD ======
        ✅ **FICHA APROBADA**
        La ficha cumple con la normativa y tiene un excelente desarrollo.
        *Recordatorio para el Staff:* 
        1. Enviar información al form de registro ⁠📑┊𝐃𝐨𝐜𝐮𝐦𝐞𝐧𝐭𝐨𝐬. 
        2. Quitar roles: Ficha rechazada / Formulario aceptado / Acceso a WL. 
        3. Añadir roles: Ciudadano / Ficha aceptada V2. 
        4. Cerrar ticket (Guardar y Eliminar).

        [SI TIENE ANTECEDENTES MÉDICOS VÁLIDOS, AGREGA ESTO]:
        **🏥 Plantilla para Antecedentes Médicos:**
        ```text
        ID Discord: [ID Discord]
        Nombre y Apellido: [Nombre del PJ]
        Fecha de nacimiento y edad: [Fecha] / [Edad]
        Antecedentes médicos: [Detalle exacto]
        ```

        [SI TIENE ANTECEDENTES PENALES VÁLIDOS, AGREGA ESTO]:
        **🚨 Plantilla para Antecedentes Penales:**
        ```text
        ID Discord: [ID Discord]
        Nombre y apellidos IC: [Nombre del PJ]
        Fecha de nacimiento y edad: [Fecha] / [Edad]
        Antecedentes penales: [Detalle exacto y tiempo en cárcel]
        ```

        ====== SI LA FICHA NO CUMPLE O LA HISTORIA ES SOSA ======
        Usa esta plantilla. Si el problema es de calidad en la historia, explícale AL USUARIO qué le falta (ej. "Tu historia es un poco apresurada, desarrolla más cómo le afectó X evento").

        ## ❌ FICHA DENEGADA ❌
        📄 Tu ficha no ha sido aprobada por el momento.

        Por favor, corrige lo siguiente:
        > - **[Nombre del apartado fallido]:** [Razonamiento claro de por qué falló o qué le falta para tener mejor calidad].

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
                "Todo mensaje enviado en este canal será evaluado detalladamente por su coherencia narrativa.\n"
                "Pega tu ficha o **adjunta tu archivo `.txt`**."
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
                    contenido_ficha = f"[DATOS DEL SISTEMA]\nID Discord del Usuario: {msg.author.id}\nAño actual del servidor: 2026\n\n[CONTENIDO DE LA FICHA]\n{msg.content}"

                    if msg.attachments:
                        for adjunto in msg.attachments:
                            if adjunto.filename.endswith('.txt'):
                                try:
                                    archivo_bytes = await adjunto.read()
                                    texto_extraido = archivo_bytes.decode('utf-8', errors='ignore')
                                    contenido_ficha += f"\n\n[CONTENIDO DEL ARCHIVO TXT]\n{texto_extraido}"
                                except Exception as e:
                                    await msg.reply(f"⚠️ No pude leer el archivo {adjunto.filename}: {e}")

                    if len(msg.content.strip()) == 0 and not msg.attachments:
                        await msg.remove_reaction("👀", self.bot.user)
                        return

                    # Usamos un poco de "temperature" (0.2) para que la IA tenga margen de razonamiento
                    # sin perder la rigidez del formato de aprobación/rechazo.
                    response = self.client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=contenido_ficha,
                        config=types.GenerateContentConfig(
                            system_instruction=self.SYSTEM_INSTRUCTION,
                            temperature=0.2 
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
