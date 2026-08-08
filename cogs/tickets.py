import discord
from discord.ext import commands, tasks
from discord import app_commands, ui
import io
import asyncio
import os
import chat_exporter
from utils.database import get_guild_data, save_guild_data, get_config, tiene_permiso

# ================= TRANSCRIPCIONES HTML PREMIUM (WEB PRIVADA) =================
async def generar_y_enviar_transcripcion(channel, guild, bot, enviar_dms=True, users=None):
    try:
        # Extraemos TODOS los mensajes para generar el HTML y ver quién habló
        msgs = [m async for m in channel.history(limit=None)]
        
        # Filtramos solo a los usuarios que escribieron al menos un mensaje en el ticket
        autores_implicados = list(set([m.author.mention for m in msgs if not m.author.bot]))

        transcript_bytes = await chat_exporter.export(
            channel,
            tz_info="America/Mexico_City",
            military_time=True,
            bot=bot
        )
        
        link_viewer = None
        emb = discord.Embed(color=0x2b2d31)
        
        if transcript_bytes:
            texto_html = transcript_bytes.decode('utf-8') if isinstance(transcript_bytes, bytes) else transcript_bytes
            file = discord.File(io.BytesIO(texto_html.encode('utf-8')), filename=f"transcript-{channel.name}.html")
            
            # Embed Oscuro Estético
            emb.set_author(name="• Transcripción de Ticket")
            emb.description = f"La transcripción de `#{channel.name}` ha sido guardada y encriptada."
            
            emb.add_field(name="➡ Ticket", value=f"#{channel.name} ({channel.id})", inline=False)
            emb.add_field(name="➡ Panel", value="TICKETS SOPORTE", inline=False)
            
            propietario = users[0] if users else None
            prop_txt = f"{propietario.name} ({propietario.id})" if propietario else "Desconocido"
            emb.add_field(name="➡ Propietario", value=prop_txt, inline=False)
            
            emb.add_field(name="➡ Usuarios implicados (Activos)", value=", ".join(autores_implicados)[:1024] if autores_implicados else "Ninguno", inline=False)
            emb.add_field(name="➡ Cantidad de mensajes", value=str(len(msgs)), inline=False)
            
            c_id = get_config(guild.id, "CANAL_TRANSCRIPCIONES_ID")
            if c_id and (c := guild.get_channel(int(c_id))):
                # 1. Enviamos el archivo oculto al log para almacenarlo en Discord
                log_msg = await c.send(embed=emb, file=file)
                
                # 2. Generamos el link apuntando a tu web en Render
                if log_msg.attachments:
                    mi_web = os.getenv("URL_RENDER", "https://rp-bot-6koq.onrender.com") 
                    link_viewer = f"{mi_web}/transcript/{c.id}/{log_msg.id}"
                    
                    view_logs = ui.View()
                    btn_ver = ui.Button(label="Ver Ticket (Web Privada)", style=discord.ButtonStyle.link, url=link_viewer, emoji="🔒")
                    view_logs.add_item(btn_ver)
                    
                    await log_msg.edit(view=view_logs)

        # ================= ENVÍO AL USUARIO POR DM =================
        if enviar_dms and users:
            for u in users:
                try: 
                    emb_dm = emb.copy()
                    emb_dm.title = "🔒 Ticket Cerrado Oficialmente"
                    emb_dm.description = f"Tu ticket **#{channel.name}** en **{guild.name}** ha sido cerrado.\nEl equipo de administración te envía la copia de tu resolución."
                    
                    if link_viewer:
                        view_dm = ui.View()
                        view_dm.add_item(ui.Button(label="Ver Mi Historial", style=discord.ButtonStyle.link, url=link_viewer, emoji="🌐"))
                        await u.send(embed=emb_dm, view=view_dm)
                    else:
                        await u.send(embed=emb_dm)
                except Exception: pass
    except Exception as e:
        print(f"[TICKETS] Error en exportador: {e}")

# ================= VISTAS DE CONTROL DE TICKET =================
class AdminTranscriptView(ui.View):
    def __init__(self, canal, guild, users):
        super().__init__(timeout=None)
        self.canal = canal; self.guild = guild; self.users = users

    @ui.button(label="Guardar y Avisar", style=discord.ButtonStyle.success, emoji="📨")
    async def btn_enviar(self, interaction: discord.Interaction, button: ui.Button):
        if not tiene_permiso(interaction.user): return await interaction.response.send_message("⛔ Permiso denegado.", ephemeral=True)
        await interaction.response.edit_message(content="Cerrando ticket...", embed=None, view=None)
        await generar_y_enviar_transcripcion(self.canal, self.guild, interaction.client, True, self.users)
        await asyncio.sleep(2)
        try: await self.canal.delete()
        except: pass

    @ui.button(label="Solo Guardar", style=discord.ButtonStyle.danger, emoji="🤫")
    async def btn_no_enviar(self, interaction: discord.Interaction, button: ui.Button):
        if not tiene_permiso(interaction.user): return await interaction.response.send_message("⛔ Permiso denegado.", ephemeral=True)
        await interaction.response.edit_message(content="Cerrando ticket...", embed=None, view=None)
        await generar_y_enviar_transcripcion(self.canal, self.guild, interaction.client, False, self.users)
        await asyncio.sleep(2)
        try: await self.canal.delete()
        except: pass

class ConfirmarCierreView(ui.View):
    def __init__(self, canal, guild, usuario):
        super().__init__(timeout=60)
        self.canal = canal; self.guild = guild; self.usuario = usuario

    @ui.button(label="✅ Sí, cerrar", style=discord.ButtonStyle.danger)
    async def btn_confirmar(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="🔒 Procesando...", view=None)
        users = []
        for target, ow in self.canal.overwrites.items():
            if isinstance(target, discord.Member) and not target.bot and ow.read_messages:
                users.append(target)
                try: await self.canal.set_permissions(target, read_messages=False)
                except Exception: pass
                    
        emb = discord.Embed(title="🔒 Cerrar", description="¿Avisar al usuario que se cerró su ticket?", color=discord.Color.gold())
        admin_roles = get_config(self.guild.id, "ROLES_ADMIN", [])
        menciones = [f"<@&{ar['id']}>" for ar in admin_roles if ar.get("ticket", False)]
        await self.canal.send(content=" ".join(menciones), embed=emb, view=AdminTranscriptView(self.canal, self.guild, users))

    @ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
    async def btn_cancelar(self, interaction: discord.Interaction, button: ui.Button): 
        await interaction.response.edit_message(content="✅ Cancelado.", view=None)

class TicketControlView(ui.View):
    def __init__(self): super().__init__(timeout=None)
    @ui.button(label="🔒 Cerrar", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="btn_cerrar_ticket")
    async def btn_cerrar(self, interaction: discord.Interaction, button: ui.Button):
        if tiene_permiso(interaction.user): 
            await interaction.response.send_message("¿Seguro que deseas cerrar este ticket?", view=ConfirmarCierreView(interaction.channel, interaction.guild, interaction.user), ephemeral=True)
        else: await interaction.response.send_message(f"⚠️ {interaction.user.mention} ha solicitado el cierre del ticket.")

# ================= VISTA DINÁMICA DE BOTONES =================
class TicketPanelView(ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        
        gdb = get_guild_data(guild_id)
        categorias = gdb.get("tickets_config", {}).get("categorias", [])
        
        if not categorias:
            categorias = [{"nombre": "Soporte", "emoji": "🛠️", "activa": True}]
            
        for cat in categorias:
            if cat.get("activa", True):
                estilo = self.determinar_color(cat["nombre"])
                btn = ui.Button(
                    label=cat["nombre"], 
                    emoji=cat.get("emoji", "🎫"), 
                    style=estilo, 
                    custom_id=f"t_din_{cat['nombre']}_{guild_id}"[:100]
                )
                btn.callback = self.crear_callback(cat["nombre"], cat.get("emoji", "🎫"))
                self.add_item(btn)

    def determinar_color(self, nombre):
        n = nombre.lower()
        if "sugerencia" in n or "donacion" in n or "compra" in n: return discord.ButtonStyle.success
        if "queja" in n or "reporte" in n or "peligro" in n or "robo" in n or "ck" in n: return discord.ButtonStyle.danger
        if "soporte" in n or "duda" in n or "morado" in n: return discord.ButtonStyle.primary
        return discord.ButtonStyle.secondary

    def crear_callback(self, nombre_cat, emoji_cat):
        async def callback(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            
            c_id = get_config(interaction.guild.id, "CATEGORIA_TICKETS_ID")
            cat_canal = interaction.guild.get_channel(int(c_id)) if c_id else getattr(interaction.channel, 'category', None)
            
            gdb = get_guild_data(interaction.guild.id)
            gdb.setdefault("tickets", {})
            gdb["tickets"][nombre_cat] = gdb["tickets"].get(nombre_cat, 0) + 1
            num = str(gdb["tickets"][nombre_cat]).zfill(3) 
            save_guild_data(interaction.guild.id, gdb)

            name = f"{emoji_cat}-{nombre_cat.lower().replace(' ', '-')}-{num}"

            ow = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False), 
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True), 
                interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True, manage_permissions=True)
            }
            
            admin_roles = get_config(interaction.guild.id, "ROLES_ADMIN", [])
            menciones = []
            for ar in admin_roles:
                if ar.get("ticket", False):
                    if role := interaction.guild.get_role(int(ar["id"])):
                        ow[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
                        menciones.append(role.mention)
                        
            try: tc = await interaction.guild.create_text_channel(name=name[:100], category=cat_canal, overwrites=ow)
            except Exception as e: return await interaction.followup.send(f"❌ Error al crear el canal. Asegúrate de que el bot tenga permisos de Administrador.\nDetalle: {e}", ephemeral=True)
            
            if "ficha" in nombre_cat.lower():
                desc = (
                    "**¿Tienes la ficha lista o dudas?**\n"
                    "Por favor, copia y pega la plantilla para llenarla (no admitimos archivos):\n\n"
                    "· URL Steam (debe estar público y verse las horas de FiveM):\n"
                    "· Edad OOC:\n\n"
                    "**FICHA DE PERSONAJE**\n"
                    "· Nombre y apellido:\n"
                    "· Fecha de nacimiento:\n"
                    "· Edad:\n"
                    "· País y Ciudad donde nació:\n"
                    "· Etnia (caucásico, asiático, latino, afrodescendiente, árabe):\n"
                    "· Lazos familiares:\n"
                    "· Descripción del personaje (física y psicológica):\n"
                    "· ¿Por qué viaja a Los Santos?:\n"
                    "· Antecedentes Penales:\n"
                    "· Antecedentes Médicos:\n"
                    "· Historia del personaje (mínimo 8 líneas):\n\n"
                    "*IMPORTANTE: TU USUARIO DE DISCORD Y STEAM DEBEN SER IGUALES.*\n"
                    "**Prohibido taguear al Staff.**"
                )
            else:
                desc = f"Describe tu consulta sobre **{nombre_cat}** y el staff te atenderá pronto.\n**Prohibido taguear al Staff.**"
                
            emb = discord.Embed(title=f"Ticket: {nombre_cat}", description=desc, color=0x2b2d31)
            await tc.send(content=f"{interaction.user.mention} {' '.join(menciones)}", embed=emb, view=TicketControlView())
            
            await interaction.followup.send(f"✅ Ticket abierto: {tc.mention}", ephemeral=True)
            
        return callback

# ================== CLASE COG PRINCIPAL ==================
class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(TicketControlView())
        
    async def cog_load(self):
        for guild in self.bot.guilds:
            gdb = get_guild_data(guild.id)
            msg_id = gdb.get("tickets_config", {}).get("panel_mensaje_id")
            if msg_id:
                try:
                    self.bot.add_view(TicketPanelView(guild.id), message_id=int(msg_id))
                except Exception: pass
                
        if not self.sincronizador_paneles.is_running():
            self.sincronizador_paneles.start()

    def cog_unload(self):
        self.sincronizador_paneles.cancel()

    @tasks.loop(minutes=1)
    async def sincronizador_paneles(self):
        for guild in self.bot.guilds:
            gdb = get_guild_data(guild.id)
            canal_id = gdb.get("tickets_config", {}).get("panel_canal_id")
            msg_id = gdb.get("tickets_config", {}).get("panel_mensaje_id")
            
            if canal_id and msg_id:
                try:
                    canal = guild.get_channel(int(canal_id))
                    if canal:
                        msg = await canal.fetch_message(int(msg_id))
                        nueva_vista = TicketPanelView(guild.id)
                        await msg.edit(view=nueva_vista)
                except Exception:
                    pass

    @sincronizador_paneles.before_loop
    async def before_sincronizador(self):
        await self.bot.wait_until_ready()

    # ================= COMANDOS DE GESTIÓN =================

    @app_commands.command(name="panel_tickets", description="Lanza el panel de tickets interactivo")
    async def panel_tickets(self, interaction: discord.Interaction):
        if not tiene_permiso(interaction.user): 
            return await interaction.response.send_message("⛔ Permiso denegado.", ephemeral=True)
            
        embed = discord.Embed(title="🎟️ SOPORTE TÉCNICO Y ATENCIÓN", description=">>> Selecciona la categoría que mejor describa tu problema.\nUn ticket privado será creado y el Staff te atenderá a la brevedad.", color=0x2b2d31)
        
        vista = TicketPanelView(interaction.guild.id)
        msg = await interaction.channel.send(embed=embed, view=vista)
        
        gdb = get_guild_data(interaction.guild.id)
        if "tickets_config" not in gdb: gdb["tickets_config"] = {"categorias": []}
        gdb["tickets_config"]["panel_canal_id"] = str(interaction.channel.id)
        gdb["tickets_config"]["panel_mensaje_id"] = str(msg.id)
        save_guild_data(interaction.guild.id, gdb)
        
        await interaction.response.send_message("✅ Panel de tickets enviado con éxito.", ephemeral=True)

    @app_commands.command(name="ticket_add", description="[TICKET] Añade a un usuario al ticket actual")
    async def ticket_add(self, interaction: discord.Interaction, usuario: discord.Member):
        if not tiene_permiso(interaction.user): 
            return await interaction.response.send_message("⛔ Permiso denegado.", ephemeral=True)
        try:
            await interaction.channel.set_permissions(usuario, read_messages=True, send_messages=True, attach_files=True)
            await interaction.response.send_message(f"✅ {usuario.mention} ha sido añadido al ticket por {interaction.user.mention}.")
        except Exception as e:
            await interaction.response.send_message(f"❌ Error al añadir usuario: {e}", ephemeral=True)

    @app_commands.command(name="ticket_remove", description="[TICKET] Elimina a un usuario del ticket actual")
    async def ticket_remove(self, interaction: discord.Interaction, usuario: discord.Member):
        if not tiene_permiso(interaction.user): 
            return await interaction.response.send_message("⛔ Permiso denegado.", ephemeral=True)
        try:
            await interaction.channel.set_permissions(usuario, overwrite=None)
            await interaction.response.send_message(f"👋 {usuario.display_name} ha sido eliminado del ticket.")
        except Exception as e:
            await interaction.response.send_message(f"❌ Error al eliminar usuario: {e}", ephemeral=True)

    @app_commands.command(name="ticket_rename", description="[TICKET] Cambia el nombre del ticket actual")
    async def ticket_rename(self, interaction: discord.Interaction, nuevo_nombre: str):
        if not tiene_permiso(interaction.user): 
            return await interaction.response.send_message("⛔ Permiso denegado.", ephemeral=True)
        try:
            nombre_limpio = nuevo_nombre.lower().replace(" ", "-")
            await interaction.channel.edit(name=nombre_limpio)
            await interaction.response.send_message(f"✅ Nombre cambiado a `#{nombre_limpio}`")
        except Exception as e:
            await interaction.response.send_message(f"❌ Error al renombrar: {e}", ephemeral=True)

    @app_commands.command(name="ticket_force_close", description="[ADMIN] Cierra un ticket de forma inmediata y guarda log.")
    async def ticket_force_close(self, interaction: discord.Interaction):
        if not tiene_permiso(interaction.user): 
            return await interaction.response.send_message("⛔ Permiso denegado.", ephemeral=True)
            
        await interaction.response.send_message("🚨 **FORZANDO CIERRE DEL TICKET...**\nGuardando transcripción...", ephemeral=False)
        
        users = []
        for target, ow in interaction.channel.overwrites.items():
            if isinstance(target, discord.Member) and not target.bot and ow.read_messages:
                users.append(target)
                
        await generar_y_enviar_transcripcion(interaction.channel, interaction.guild, interaction.client, False, users)
        await asyncio.sleep(2)
        try: await interaction.channel.delete()
        except Exception: pass

async def setup(bot):
    await bot.add_cog(Tickets(bot))
