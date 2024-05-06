import random
import os

HTML_DIRECTORY = '.'
IMG_DIRECTORY = '/home/batman/Photos/'
IMG_DIRECTORY = '/media/batman/COLD_BACKUP/pCloud/Fotos/'
IMG_OK_EXTS = ['.jpg', '.jpeg', '.png']
MAX_IMGS_PER_ALBUM = 3


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
    files = [os.path.join(path, f) for f in lsImgs(os.path.join(dirs_base_path, path))]
    files = random.sample(files, min(n, len(files)))
    files.sort()
    return files


class Foo:
    def __init__(self, img_directory):
        self.img_directory = img_directory
        self.albums = lsDirs(img_directory)
        self.max_imgs_per_album = MAX_IMGS_PER_ALBUM
        self.curr_imgs = []

    def next(self):
        tries = 10
        while len(self.curr_imgs) == 0:
            print("Run out of images, selecting new album")
            self.curr_imgs = randomSelectImgs(self.max_imgs_per_album, self.img_directory, self.albums)
            tries -= 1
            if tries <= 0:
                raise RuntimeError("Can't find path with images")

        return self.curr_imgs.pop(0)


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

if __name__ == '__main__':
    app.run(debug=True)
