import random
import os
import json
import json
import exifread

HTML_DIRECTORY = '.'
IMG_DIRECTORY = '/home/batman/extstorage/www_slide'
IMG_OK_EXTS = ['.jpg', '.jpeg', '.png']
MAX_IMGS_PER_ALBUM = 10

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

def extract_exif(img_fullpath):
    exif = {}
    with open(img_fullpath, 'rb') as fp:
        tags = exifread.process_file(fp, details=False)
        for k,v in tags.items():
            exif[k] = str(v)
        exif["gps"] = extract_gps(tags)
    return exif

class Foo:
    def __init__(self, img_directory):
        self.img_directory = img_directory
        self.albums = lsDirs(img_directory)
        print(f"Found {len(self.albums)} albums")
        self.max_imgs_per_album = MAX_IMGS_PER_ALBUM
        self.album_path = None
        self.curr_imgs = []
        self.curr_img_idx = 0

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
            "image_exif": extract_exif(img_fullpath),
        }

        return json.dumps(meta)


from flask import Flask, send_from_directory

app = Flask(__name__)


@app.route('/')
def index():
    return send_from_directory(HTML_DIRECTORY, 'index.html')

foo = Foo(IMG_DIRECTORY)
@app.route('/get_image')
def get_image():
    img = foo.next()
    return send_from_directory(IMG_DIRECTORY, img)

@app.route('/<path:path>')
def serve_html(path):
    return send_from_directory(HTML_DIRECTORY, path)

@app.route('/ctrl')
def ctrl():
    return foo.meta()

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0")
