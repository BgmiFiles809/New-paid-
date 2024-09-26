import socketio
import time
import json
import requests
import threading

# Worker details
WORKER_ID = 'worker_1'
WORKER_NAME = 'My Worker'

# SocketIO client
sio = socketio.Client()

# API endpoint for registering the worker
register_url = 'https://lm6000k.pythonanywhere.com/register_worker'

# Register worker function
def register_worker():
    headers = {
        'API-Key': 'fukbgmiservernow'
    }
    data = {
        'worker_id': WORKER_ID,
        'worker_name': WORKER_NAME
    }
    response = requests.post(register_url, json=data, headers=headers)
    if response.status_code == 200:
        print(f"Worker {WORKER_ID} registered successfully.")
    else:
        print(f"Failed to register worker: {response.text}")

# Heartbeat function
def send_heartbeat():
    while True:
        time.sleep(5)
        headers = {
            'API-Key': 'fukbgmiservernow'
        }
        data = {
            'worker_id': WORKER_ID
        }
        response = requests.post('https://lm6000k.pythonanywhere.com/worker_heartbeat', json=data, headers=headers)
        print(response.json())

# Handle connection
@sio.event
def connect():
    print('Connected to server')
    sio.emit('join', {'worker_id': WORKER_ID})

# Handle task notifications
@sio.event
def new_task(data):
    print(f"Received new task: {data}")

# Handle disconnection
@sio.event
def disconnect():
    print('Disconnected from server')

# Attempt to connect to the server
try:
    sio.connect('https://lm6000k.pythonanywhere.com/socket.io/')  # Correct URL
    register_worker()

    # Start heartbeat in a separate thread
    heartbeat_thread = threading.Thread(target=send_heartbeat)
    heartbeat_thread.start()

    # Keep the client running
    while True:
        time.sleep(1)

except socketio.exceptions.ConnectionError as e:
    print(f"Connection failed: {e}")
except Exception as e:
    print(f"An error occurred: {e}")
finally:
    sio.disconnect()
