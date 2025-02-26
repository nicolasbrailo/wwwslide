from albums import Albums
from clients import Clients
from flask import Flask, send_from_directory
from image_sender import ImageSender
import json
import threading
import time

with open("config.json", 'r') as fp:
    CONF = json.load(fp)

flask_app = Flask(__name__)

albums = Albums(CONF)
img_sender = ImageSender(CONF, flask_app)
clients = Clients(CONF, flask_app, albums, img_sender)

@flask_app.route('/')
def serve_html():
    return send_from_directory('html', 'index.html')
@flask_app.route('/favicon.ico')
def favicon():
    return send_from_directory('html', 'favicon.ico')
@flask_app.route('/css/<path:p>')
def serve_css(p):
    return send_from_directory('html/css', p)
@flask_app.route('/js/<path:p>')
def serve_js(p):
    return send_from_directory('html/js', p)

# Set up cleanup crons
def bg_clients_clean():
    while True:
        clients.cleanup_stale_clients()
        time.sleep(clients.client_stale_threshold_secs)

def bg_cache_clean():
    while True:
        print('Clean up old files...')
        cnt = img_sender.cleanup_cache()
        print(f'Removed {cnt} old files...')
        # Sleep for a day
        time.sleep(60 * 60 * 24)

cleanup_clients_th = threading.Thread(target=bg_clients_clean)
cleanup_clients_th.daemon = True  # Daemon thread will exit when the main program exits
cleanup_clients_th.start()

cleanup_cache_th = threading.Thread(target=bg_cache_clean)
cleanup_cache_th.daemon = True
cleanup_cache_th.start()

if __name__ == '__main__':
    flask_app.run(debug=True, host="0.0.0.0")

