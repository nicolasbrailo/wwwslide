## import threading
## import time
## from datetime import datetime, timedelta
## def delete_old_files(directory, days_threshold):
##     try:
##         threshold_date = datetime.now() - timedelta(days=days_threshold)
##         files = os.listdir(directory)
##         for file in files:
##             file_path = os.path.join(directory, file)
## 
##             if os.path.isfile(file_path):
##                 last_modified_time = datetime.fromtimestamp(os.path.getmtime(file_path))
## 
##                 if last_modified_time < threshold_date:
##                     os.remove(file_path)
##                     print(f'Cleanup old cache {file_path}')
## 
##     except Exception as e:
##         print('Failed to cleanup old cached assets: ' + str(e))
## 
## def setup_cleanup_cache(cache_dir):
##     def run():
##         while True:
##             print('Clean up old files')
##             delete_old_files(cache_dir, 1)
##             # Sleep for a day
##             time.sleep(60 * 60 * 24)
##     cleanup_cache_th = threading.Thread(target=run)
##     cleanup_cache_th.daemon = True  # Daemon thread will exit when the main program exits
##     cleanup_cache_th.start()
## 
### 
### setup_cleanup_cache(CONF["img_cache_directory"])
### 
### @app.route('/<path:path>')
### def serve_html(path):
###     return send_from_directory(HTML_DIRECTORY, path)


from flask import Flask, send_from_directory
import json
from albums import Albums
from clients import Clients
from image_sender import ImageSender

with open("config.json", 'r') as fp:
    CONF = json.load(fp)

flask_app = Flask(__name__)

albums = Albums(CONF)
img_sender = ImageSender(CONF, flask_app)
clients = Clients(CONF, flask_app, albums, img_sender)

if __name__ == '__main__':
    flask_app.run(debug=True, host="0.0.0.0")

