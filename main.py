from flask import Flask, send_from_directory
from pymethodecache.cache import cache_func
import exifread
import json
import json
import os
import random
import requests

HTML_DIRECTORY = '.'
IMG_OK_EXTS = ['.jpg', '.jpeg', '.png']

def lsImgs(path):
    interesting = lambda p: os.path.isfile(p) and os.path.splitext(p)[1].lower() in IMG_OK_EXTS
    imgs = [f for f in os.listdir(path) if interesting(os.path.join(path, f))]
    imgs.sort()
    return imgs

def lsDirs(base_path):
    directories = []
    for dirpath, dirnames, _ in os.walk(base_path):
        relative_path = os.path.relpath(dirpath, base_path)
        full_path = os.path.join(base_path, relative_path)
        if not relative_path.startswith('.') and len(lsImgs(full_path)) != 0:
            directories.append(relative_path)
    return directories

def randomSelectImgs(n, dirs_base_path, dirs):
    if len(dirs) == 0:
        return []
    path = dirs[random.randint(0, len(dirs)-1)]
    print("Select images from " + path)
    files = [os.path.join(path, f) for f in lsImgs(os.path.join(dirs_base_path, path))]
    files = random.sample(files, min(n, len(files)))
    files.sort()
    return path, files

@cache_func('cache/wget.pkl')
def wget(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:128.0) Gecko/20100101 Firefox/128.0',
    }
    response = requests.get(url, headers=headers)
    content = response.content.decode('utf-8')
    return content

def extract_keys(dic, interesting_keys):
    return {k: dic[k] for k in interesting_keys if k in dic}

def revgeo(geo_api_key, lat, lon):
    url = f"https://api.geoapify.com/v1/geocode/reverse?lat={round(lat, 3)}&lon={round(lon, 3)}&format=json&apiKey={geo_api_key}"
    try:
        loc_req = wget(url)
        loc = json.loads(loc_req)["results"][0]
        if "formatted" in loc:
            loc["revgeo"] = loc["formatted"]
        filt_loc = extract_keys(loc, ["country", "state", "city", "postcode", "revgeo", "address_line1", "address_line2"])
        return filt_loc
    except KeyError:
        return None

def convert_to_degrees(value):
    """Helper function to convert the GPS coordinates stored in EXIF format to degrees."""
    d = float(value.values[0].num) / float(value.values[0].den)
    m = float(value.values[1].num) / float(value.values[1].den)
    s = float(value.values[2].num) / float(value.values[2].den)
    return d + (m / 60.0) + (s / 3600.0)

def extract_gps(tags):
    if not tags or \
       not tags.get('GPS GPSLatitude') or \
       not tags.get('GPS GPSLatitudeRef') or \
       not tags.get('GPS GPSLongitude') or \
       not tags.get('GPS GPSLongitudeRef'):
        return None
    lat = convert_to_degrees(tags.get('GPS GPSLatitude'))
    lon = convert_to_degrees(tags.get('GPS GPSLongitude'))
    if tags.get('GPS GPSLatitudeRef').values[0] != 'N':
        lat = -lat
    if tags.get('GPS GPSLongitudeRef').values[0] != 'E':
        lon = -lon
    return {"lat": lat, "lon": lon}

def extract_all_exif(img_fullpath, rev_geo_apikey):
    exif = {}
    with open(img_fullpath, 'rb') as fp:
        tags = exifread.process_file(fp, details=False)
        for k,v in tags.items():
            exif[k] = str(v)
        exif["gps"] = extract_gps(tags)

    if exif["gps"]:
        exif["reverse_geo"] = revgeo(rev_geo_apikey, exif["gps"]["lat"], exif["gps"]["lon"])
    else:
        exif["reverse_geo"] = None

    return exif

def extract_exif(img_fullpath, rev_geo_apikey):
    exif = extract_all_exif(img_fullpath, rev_geo_apikey)
    interesting_meta = ["gps", "reverse_geo", "EXIF ExifImageWidth", "EXIF ExifImageLength", "EXIF DateTimeOriginal", "Image Make", "Image Model"]
    return extract_keys(exif, interesting_meta)


from PIL import Image, ImageDraw
import qrcode

def make_qr(url, w, h):
    qr = qrcode.QRCode(
        version=1,  # Controls the size of the QR code (1 is 21x21 matrix)
        error_correction=qrcode.constants.ERROR_CORRECT_L,  # About 7% error correction
        box_size=10,  # Size of each box in pixels
        border=1,  # Thickness of the border
    )

    qr.add_data(url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill="black", back_color="white")

    # Adjust the size as needed
    qr_img = qr_img.resize((w, h))
    return qr_img

def add_qr_to_img(img_path, img_out_path, qr_url):
    base_image = Image.open(img_path)
    width, height = base_image.size
    QR_PCT_SZ = 0.1
    qrsz = max(int(QR_PCT_SZ * width), int(QR_PCT_SZ * height))

    qr = make_qr(qr_url, qrsz, qrsz)

    # Step 4: Paste the QR code onto the base image as a watermark
    # You can position it as needed (here it's at the bottom-right corner)
    position = (base_image.width - qr.width - 10, base_image.height - qr.height - 10)
    base_image.paste(qr, position)

    base_image.save(img_out_path, "JPEG")

import urllib.parse
def mk_image_hash(fpath):
    return urllib.parse.quote_plus(fpath)
def mk_image_path_from_hash(hashedpath):
    return urllib.parse.unquote_plus(hashedpath)

class AlbumMgr:
    def __init__(self, conf):
        try:
            self.rev_geo_apikey = conf["rev_geo_apikey"]
        except KeyError:
            self.rev_geo_apikey = None
        self.img_directory = conf["img_directory"]
        self.albums = lsDirs(conf["img_directory"])
        print(f"Found {len(self.albums)} albums")
        self.max_imgs_per_album = int(conf["max_images_per_random_album"])
        self.album_path = None
        self.curr_imgs = []
        self.curr_img_idx = 0

    def select_new_album(self, img_new_album=None):
        self.curr_imgs = []
        self.curr_img_idx = 0
        if img_new_album is None:
            self.next()
            return True
        else:
            try:
                self.album_path = os.path.dirname(img_new_album)
                path = os.path.join(self.img_directory, self.album_path)
                self.curr_imgs = [os.path.join(path, f) for f in lsImgs(path)]
                self.curr_img_idx = 0
                return True
            except FileNotFoundError:
                return False

    def next(self):
        if self.curr_img_idx+1 >= len(self.curr_imgs):
            self.curr_imgs = []
            self.curr_img_idx = 0

        tries = 10
        while len(self.curr_imgs) == 0:
            print("Run out of images, selecting new album")
            self.album_path, self.curr_imgs = randomSelectImgs(self.max_imgs_per_album, self.img_directory, self.albums)
            tries -= 1
            if tries <= 0:
                raise RuntimeError("Can't find path with images")

        self.curr_img_idx += 1
        return self.curr_imgs[self.curr_img_idx]

    def meta(self):
        if self.curr_img_idx >= len(self.curr_imgs):
            return json.dumps({})

        img_path = self.curr_imgs[self.curr_img_idx]
        img_fullpath = os.path.join(self.img_directory, img_path)
        meta = {
            "album_path": self.album_path,
            "image_index": self.curr_img_idx,
            "image_count": len(self.curr_imgs),
            "image_path": img_path,
            "image_full_path": img_fullpath,
            "image_exif": extract_exif(img_fullpath, self.rev_geo_apikey),
        }

        return json.dumps(meta)


with open("config.json", 'r') as fp:
    CONF = json.load(fp)

albums = AlbumMgr(CONF)
app = Flask(__name__)

@app.route('/')
def index():
    return send_from_directory(HTML_DIRECTORY, 'index.html')

@app.route('/get_image')
def get_image():
    img = albums.next()
    hashedpath = mk_image_hash(img)
    qr_url = CONF["service_url"] + '/rc/' + hashedpath
    img_out_path = os.path.join(CONF["img_cache_directory"], hashedpath)

    print(qr_url, img_out_path)

    # TODO: if fexists img_out_path: skip gen image
    # TODO: limit cache size
    add_qr_to_img(os.path.join(CONF["img_directory"], img), img_out_path, qr_url)
    return send_from_directory(CONF["img_cache_directory"], hashedpath, download_name=hashedpath)

@app.route('/get_image_raw/<path:hashedpath>')
def get_image_raw(hashedpath):
    img = mk_image_path_from_hash(hashedpath)
    return send_from_directory(CONF["img_directory"], img, download_name=hashedpath)

@app.route('/get_image_meta/<path:hashedpath>')
def get_image_meta(hashedpath):
    img_path = mk_image_path_from_hash(hashedpath)
    img_fullpath = os.path.join(CONF["img_directory"], img_path)
    meta = {
        "album_path": albums.album_path,
        "image_index": albums.curr_img_idx,
        "image_count": len(albums.curr_imgs),
        "image_path": img_path,
        "image_full_path": img_fullpath,
        "image_exif": extract_exif(img_fullpath, CONF["rev_geo_apikey"]),
    }
    return json.dumps(meta)

@app.route("/new_random_album")
def new_random_album():
    return "OK" if albums.select_new_album() else "Can't find album"

@app.route("/see_complete_album/<path:hashedpath>")
def see_complete_album(hashedpath):
    img_path = mk_image_path_from_hash(hashedpath)
    return "OK" if albums.select_new_album(img_path) else "Can't find album"

@app.route('/rc')
@app.route('/rc/<path:hashedpath>')
def rc(hashedpath=None):
    img_path = mk_image_path_from_hash(hashedpath)
    img_fullpath = os.path.join(CONF["img_directory"], img_path)
    exif = extract_exif(img_fullpath, CONF["rev_geo_apikey"])
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" href="/favicon.ico" type="image/x-icon">
    <link rel="stylesheet" href="/css/magick.min.css">
    <link rel="stylesheet" href="/css/style.css">
    <title>wwwslide</title>
</head>
<body>
<div width="99%" display="block">
Picture: {img_path}<br>
Taken: {exif["EXIF DateTimeOriginal"]}<br/>
Where: {exif["reverse_geo"]["revgeo"]}<br/>
Cam: {exif["Image Make"]} {exif["Image Model"]}<br/>
<a href="/new_random_album">New random album</a></br>
<a href="/see_complete_album/{hashedpath}">See full album</a></br>
</div>
</body>
</html>
"""


@app.route('/<path:path>')
def serve_html(path):
    return send_from_directory(HTML_DIRECTORY, path)

@app.route('/meta')
def meta():
    return albums.meta()


if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0")
