from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Servidor Web del Bot Activo."

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive(bot=None):
    t = Thread(target=run)
    t.start()
