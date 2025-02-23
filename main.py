
## from pymethodecache.cache import cache_func
## import exifread
## import os
## import random
## import requests
## 
## 
## HTML_DIRECTORY = '.'
## 
## @cache_func('cache/wget.pkl')
## def wget(url):
##     headers = {
##         'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:128.0) Gecko/20100101 Firefox/128.0',
##     }
##     response = requests.get(url, headers=headers)
##     content = response.content.decode('utf-8')
##     return content
## 
## def extract_keys(dic, interesting_keys):
##     return {k: dic[k] for k in interesting_keys if k in dic}
## 
## def revgeo(geo_api_key, lat, lon):
##     url = f"https://api.geoapify.com/v1/geocode/reverse?lat={round(lat, 3)}&lon={round(lon, 3)}&format=json&apiKey={geo_api_key}"
##     try:
##         loc_req = wget(url)
##         loc = json.loads(loc_req)["results"][0]
##         if "formatted" in loc:
##             loc["revgeo"] = loc["formatted"]
##         filt_loc = extract_keys(loc, ["country", "state", "city", "postcode", "revgeo", "address_line1", "address_line2"])
##         return filt_loc
##     except KeyError:
##         return None
## 
## def convert_to_degrees(value):
##     """Helper function to convert the GPS coordinates stored in EXIF format to degrees."""
##     d = float(value.values[0].num) / float(value.values[0].den)
##     m = float(value.values[1].num) / float(value.values[1].den)
##     s = float(value.values[2].num) / float(value.values[2].den)
##     return d + (m / 60.0) + (s / 3600.0)
## 
## def extract_gps(tags):
##     if not tags or \
##        not tags.get('GPS GPSLatitude') or \
##        not tags.get('GPS GPSLatitudeRef') or \
##        not tags.get('GPS GPSLongitude') or \
##        not tags.get('GPS GPSLongitudeRef'):
##         return None
##     lat = convert_to_degrees(tags.get('GPS GPSLatitude'))
##     lon = convert_to_degrees(tags.get('GPS GPSLongitude'))
##     if tags.get('GPS GPSLatitudeRef').values[0] != 'N':
##         lat = -lat
##     if tags.get('GPS GPSLongitudeRef').values[0] != 'E':
##         lon = -lon
##     return {"lat": lat, "lon": lon}
## 
## def extract_all_exif(img_fullpath, rev_geo_apikey):
##     exif = {}
##     with open(img_fullpath, 'rb') as fp:
##         tags = exifread.process_file(fp, details=False)
##         for k,v in tags.items():
##             exif[k] = str(v)
##         exif["gps"] = extract_gps(tags)
## 
##     if exif["gps"]:
##         exif["reverse_geo"] = revgeo(rev_geo_apikey, exif["gps"]["lat"], exif["gps"]["lon"])
##     else:
##         exif["reverse_geo"] = None
## 
##     return exif
## 
## def extract_exif(img_fullpath, rev_geo_apikey):
##     exif = extract_all_exif(img_fullpath, rev_geo_apikey)
##     interesting_meta = ["gps", "reverse_geo", "EXIF ExifImageWidth", "EXIF ExifImageLength", "EXIF DateTimeOriginal", "Image Make", "Image Model"]
##     return extract_keys(exif, interesting_meta)
##
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
## 

### class AlbumMgr:
### 
#        try:
#            self.rev_geo_apikey = conf["rev_geo_apikey"]
#        except KeyError:
#            self.rev_geo_apikey = None
#
###     def select_new_album(self, img_new_album=None):
###         self.curr_imgs = []
###         self.curr_img_idx = 0
###         if img_new_album is None:
###             self.next()
###             return True
###         else:
###             try:
###                 self.album_path = os.path.dirname(img_new_album)
###                 path = os.path.join(self.img_directory, self.album_path)
###                 self.curr_imgs = [os.path.join(path, f) for f in lsImgs(path)]
###                 self.curr_img_idx = 0
###                 return True
###             except FileNotFoundError:
###                 return False
### 
###     def next(self):
###         if self.curr_img_idx+1 >= len(self.curr_imgs):
###             self.curr_imgs = []
###             self.curr_img_idx = 0
### 
###         tries = 10
###         while len(self.curr_imgs) == 0:
###             print("Run out of images, selecting new album")
###             self.album_path, self.curr_imgs = randomSelectImgs(self.max_imgs_per_album, self.img_directory, self.albums)
###             tries -= 1
###             if tries <= 0:
###                 raise RuntimeError("Can't find path with images")
### 
###         self.curr_img_idx += 1
###         return self.curr_imgs[self.curr_img_idx]
### 
###     def meta(self):
###         if self.curr_img_idx >= len(self.curr_imgs):
###             return json.dumps({})
### 
###         img_path = self.curr_imgs[self.curr_img_idx]
###         img_fullpath = os.path.join(self.img_directory, img_path)
###         meta = {
###             "album_path": self.album_path,
###             "image_index": self.curr_img_idx,
###             "image_count": len(self.curr_imgs),
###             "image_path": img_path,
###             "image_full_path": img_fullpath,
###             "image_exif": extract_exif(img_fullpath, self.rev_geo_apikey),
###         }
### 
###         return json.dumps(meta)
## 
## 
### 
### albums = AlbumMgr(CONF)
### 
### setup_cleanup_cache(CONF["img_cache_directory"])
### 
### @app.route('/get_image_raw/<path:hashedpath>')
### def get_image_raw(hashedpath):
###     img = mk_image_path_from_hash(hashedpath)
###     return send_from_directory(CONF["img_directory"], img, download_name=hashedpath)
### 
### @app.route('/get_image_meta/<path:hashedpath>')
### def get_image_meta(hashedpath):
###     img_path = mk_image_path_from_hash(hashedpath)
###     img_fullpath = os.path.join(CONF["img_directory"], img_path)
###     meta = {
###         "album_path": albums.album_path,
###         "image_index": albums.curr_img_idx,
###         "image_count": len(albums.curr_imgs),
###         "image_path": img_path,
###         "image_full_path": img_fullpath,
###         "image_exif": extract_exif(img_fullpath, CONF["rev_geo_apikey"]),
###     }
###     return json.dumps(meta)
### 
### @app.route("/new_random_album")
### def new_random_album():
###     return "OK" if albums.select_new_album() else "Can't find album"
### 
### @app.route("/see_complete_album/<path:hashedpath>")
### def see_complete_album(hashedpath):
###     img_path = mk_image_path_from_hash(hashedpath)
###     return "OK" if albums.select_new_album(img_path) else "Can't find album"
### 
### @app.route('/rc')
### @app.route('/rc/<path:hashedpath>')
### def rc(hashedpath=None):
###     img_path = mk_image_path_from_hash(hashedpath)
###     img_fullpath = os.path.join(CONF["img_directory"], img_path)
###     exif = extract_exif(img_fullpath, CONF["rev_geo_apikey"])
###     return f"""
### <!DOCTYPE html>
### <html lang="en">
### <head>
###     <meta charset="UTF-8">
###     <meta name="viewport" content="width=device-width, initial-scale=1.0">
###     <link rel="icon" href="/favicon.ico" type="image/x-icon">
###     <link rel="stylesheet" href="/css/magick.min.css">
###     <link rel="stylesheet" href="/css/style.css">
###     <title>wwwslide</title>
### </head>
### <body>
### <div width="99%" display="block">
### Picture: {img_path}<br>
### Taken: {exif["EXIF DateTimeOriginal"]}<br/>
### Where: {exif["reverse_geo"]["revgeo"]}<br/>
### Cam: {exif["Image Make"]} {exif["Image Model"]}<br/>
### <a href="/new_random_album">New random album</a></br>
### <a href="/see_complete_album/{hashedpath}">See full album</a></br>
### </div>
### </body>
### </html>
### """
### 
### 
### @app.route('/<path:path>')
### def serve_html(path):
###     return send_from_directory(HTML_DIRECTORY, path)
### 
### @app.route('/meta')
### def meta():
###     return albums.meta()


from flask import Flask, send_from_directory
import json
from albums import Albums
from clients import Clients
from image_sender import ImageSender

with open("config.json", 'r') as fp:
    CONF = json.load(fp)

flask_app = Flask(__name__)

albums = Albums(CONF)
img_sender = ImageSender(CONF)
clients = Clients(CONF, flask_app, albums, img_sender)

@flask_app.route('/qr/<path:imghash>')
def qr(imghash):
    return imghash

if __name__ == '__main__':
    flask_app.run(debug=True, host="0.0.0.0")

