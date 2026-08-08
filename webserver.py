import os
import logging
from flask import Flask
from threading import Thread

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask('')

@app.route('/')
def home():
    return "Servidor Web del Bot Activo y funcionando en Render 🚀"

def run():
    port = int(os.environ.get("PORT", 8080))
    print(f"🌐 Iniciando servidor web en el puerto {port}...")
    app.run(host='0.0.0.0', port=port)

def keep_alive(bot=None):
    t = Thread(target=run)
    t.start()
