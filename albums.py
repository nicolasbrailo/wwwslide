import os
import random

def lsImgs(path, allowed_extensions):
    interesting = lambda p: os.path.isfile(p) and os.path.splitext(p)[1].lower() in allowed_extensions
    imgs = [f for f in os.listdir(path) if interesting(os.path.join(path, f))]
    imgs.sort()
    return imgs

def lsDirs(base_path, allowed_extensions):
    if not os.path.exists(base_path) or not os.path.isdir(base_path):
        raise ValueError(f"Can't find albums base path {base_path}, doesn't exist")

    directories = []
    print(f"Scanning {base_path} for albums...")
    for dirpath, dirnames, _ in os.walk(base_path):
        relative_path = os.path.relpath(dirpath, base_path)
        full_path = os.path.join(base_path, relative_path)
        if not relative_path.startswith('.') and len(lsImgs(full_path, allowed_extensions)) != 0:
            directories.append(relative_path)
    print(f"Found {len(directories)} albums")
    return directories

def get_random_files(cnt, path, allowed_extensions):
    if '..' in path:
        raise ValueError(f"Bad path {album_path}")
    if not os.path.isdir(path):
        raise ValueError("{album_path} is not a valid directory")
    if len(allowed_extensions) == 0:
        raise ValueError("No valid img extensions provided")

    files = [
        os.path.join(path, f) for f in os.listdir(path)
        if os.path.isfile(os.path.join(path, f)) and f.lower().endswith(tuple(allowed_extensions))
    ]

    return random.sample(files, min(cnt, len(files)))

class Albums:
    def __init__(self, conf):
        self.img_directory = conf["img_directory"]
        self.allowed_extensions = [x.lower() for x in conf["allowed_extensions"]]
        self.albums = lsDirs(self.img_directory, self.allowed_extensions)

    def get_random(self):
        return self.albums[random.randint(0, len(self.albums)-1)]

    def random_select_pictures(self, album_path, max_images_cnt):
        return get_random_files(
                max_images_cnt,
                os.path.join(self.img_directory, album_path),
                self.allowed_extensions)

