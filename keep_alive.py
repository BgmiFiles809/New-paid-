from flask import Flask, render_template
from threading import Thread

app = Flask(__name__)
@app.route('/')
def index():
    return "Alive"

def run():
    app.run(host='0.0.0.0',port=8080)

def run():
    app.run(host='0.0.0.0',port=1111)

def run():
    app.run(host='0.0.0.0',port=8888)



def keep_alive():
    t = Thread(target=run)
    t.start()    