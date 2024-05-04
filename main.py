import random
import os

def lsDirs(base_path):
    directories = []
    for dirpath, dirnames, _ in os.walk(base_path):
        relative_path = os.path.relpath(dirpath, base_path)
        if relative_path != '.':
            directories.append(relative_path)
    return directories

def ls(path):
    interesting = lambda p: os.path.isfile(p) #and os.path.splitext(p)[0].lower() in ['jpg']
    return [f for f in os.listdir(path) if interesting(os.path.join(path, f))]

class Foo:
    def __init__(self, img_directory):
        self.img_directory = img_directory
        self.known_albums = lsDirs(img_directory)
        for a in self.known_albums:
            print("Discovered ", a)

        self.currAlbIdx = None
        self.currImgs = None
        self.max_imgs_per_album = 3

    def next(self):
        if self.currAlbIdx is None:
            self.currAlbIdx = random.randint(0, len(self.known_albums))
            print("Selected new album ", self.known_albums[self.currAlbIdx])

        if self.currImgs is None:
            files = ls(os.path.join(self.img_directory, self.known_albums[self.currAlbIdx]))
            self.currImgs = random.sample(files, min(self.max_imgs_per_album, len(files)))

        imgpath = 'Nope'
        if len(self.currImgs) != 0:
            imgpath = os.path.join(self.known_albums[self.currAlbIdx], self.currImgs.pop())

        if len(self.currImgs) == 0:
            self.currImgs = None
            self.currAlbIdx = None

        return imgpath



from flask import Flask, send_from_directory

app = Flask(__name__)

# Specify the directory containing the HTML files
html_directory = '.'
img_directory = '/home/batman/Photos/'

@app.route('/')
def index():
    # Serve the index.html file
    return send_from_directory(html_directory, 'index.html')

foo = Foo(img_directory)
@app.route('/get_image')
def get_image():
    img = foo.next()
    print(img)
    return send_from_directory(img_directory, img)

@app.route('/<path:path>')
def serve_html(path):
    # Serve HTML files from the specified directory
    return send_from_directory(html_directory, path)

if __name__ == '__main__':
    app.run(debug=True)
