from datetime import datetime, timedelta
from flask import send_file
from img_meta import get_img_meta
from PIL import Image
import os
import qrcode
import time
import urllib.parse

def delete_old_files(directory, threshold_days=1):
    cnt = 0
    threshold_seconds = threshold_days * 86400
    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            try:
                file_mtime = os.stat(file_path).st_mtime
                if time.time() - file_mtime > threshold_seconds:
                    os.remove(file_path)
                    cnt = cnt + 1
                    print(f"Deleted: {file_path}")
            except Exception as e:
                print(f"Error removing {file_path}: {e}")

    return cnt


def mk_image_hash(cfg, path):
    return cfg["service_url"] + '/img/qr/' + urllib.parse.quote_plus(path)

def img_path_from_hash(imghash):
    return '/' + urllib.parse.unquote_plus(imghash)

def make_qr(cfg, path, w, h):
    qr = qrcode.QRCode(
        version=1,  # Controls the size of the QR code (1 is 21x21 matrix)
        error_correction=qrcode.constants.ERROR_CORRECT_L,  # About 7% error correction
        box_size=10,  # Size of each box in pixels
        border=1,  # Thickness of the border
    )

    qr.add_data(mk_image_hash(cfg, path))
    qr.make(fit=True)
    qr_img = qr.make_image(fill="black", back_color="white")

    # Adjust the size as needed
    qr_img = qr_img.resize((w, h))
    return qr_img

def _maybe_mogrify_image(cfg, client_cfg, img_path):
    if not img_path.startswith(cfg["img_directory"]):
        raise ValueError(f"Invalid image path {img_path}")

    if client_cfg["target_width"] is None != client_cfg["target_height"] is None:
        raise ValueError(f"Client must set both target_width and target_height")

    if client_cfg["target_width"] is None and client_cfg["target_height"] is None and not client_cfg['embed_info_qr_code']:
        # Client wants raw image
        return img_path

    if len(cfg["img_cache_directory"]) < 2 or not os.path.exists(cfg["img_cache_directory"]) or not os.path.isdir(cfg["img_cache_directory"]):
        raise ValueError(f"Cache directory {cfg['img_cache_directory']} doesn't exist or isn't a directory")

    img = Image.open(img_path)
    width, height = img.size
    if client_cfg["target_width"] is None:
        resize_needed = False
    else:
        resize_needed = width > client_cfg["target_width"] or height > client_cfg["target_height"]
    if not resize_needed and not client_cfg['embed_info_qr_code']:
        # No resize or QR needed
        return img_path

    # If we're here, we need to either resize or add a QR code

    # Remove the base path of the image to be resized, so that we can cache it per album
    album_and_fname = img_path[len(cfg["img_directory"]):]
    if album_and_fname[0] == '/':
        album_and_fname = album_and_fname[1:]
    qr_cache_name = "qr" if client_cfg['embed_info_qr_code'] else "noqr"
    cache_settings = f"{client_cfg['target_width']}x{client_cfg['target_height']}_{qr_cache_name}"
    cached_img_path = os.path.join(cfg["img_cache_directory"], cache_settings, album_and_fname)

    if os.path.exists(cached_img_path):
        return cached_img_path

    cache_path = os.path.dirname(cached_img_path)
    try:
        os.makedirs(cache_path, exist_ok=True)
    except Exception as e:
        raise ValueError(f"Failed to mogrify '{img_path}': can't create cache dir at {cache_path} for mogrified image {cached_img_path}: {e}")

    if resize_needed:
        img.thumbnail((client_cfg["target_width"], client_cfg["target_height"]))

    if client_cfg['embed_info_qr_code']:
       QR_PCT_SZ = 0.1
       width, height = img.size
       qrsz = max(int(QR_PCT_SZ * width), int(QR_PCT_SZ * height))
       qr = make_qr(cfg, img_path, qrsz, qrsz)
       # Paste the QR code onto the base image as a watermark
       # You can position it as needed (here it's at the bottom-right corner)
       position = (img.width - qr.width - 10, img.height - qr.height - 10)
       img.paste(qr, position)

    img.save(cached_img_path)
    return cached_img_path

class ImageSender:
    def __init__(self, conf, flask_app):
        self.cfg = {
            "img_cache_directory": conf["img_cache_directory"],
            "img_directory":  conf["img_directory"],
            "service_url":  conf["service_url"],
            "rev_geo_apikey": conf["rev_geo_apikey"],
        }

        if not os.path.exists(self.cfg["img_cache_directory"]) or not os.path.isdir(self.cfg["img_cache_directory"]):
            raise ValueError(f"Cache directory {self.img_cache_directory} doesn't exist or isn't a directory")

        flask_app.add_url_rule("/img/qr/<path:imghash>", "img_qr", self.img_qr)
        flask_app.add_url_rule("/img/raw/<path:imghash>", "img_raw", self.img_raw)

    def send_image(self, client_cfg, path):
        path = _maybe_mogrify_image(self.cfg, client_cfg, path)
        return send_file(path)

    def get_image_meta(self, imgpath):
        return get_img_meta(self.cfg["img_directory"], imgpath, self.cfg["rev_geo_apikey"])

    def img_qr(self, imghash):
        imgpath = img_path_from_hash(imghash)
        return get_img_meta(self.cfg["img_directory"], imgpath, self.cfg["rev_geo_apikey"])

    def img_raw(self, imghash):
        imgpath = img_path_from_hash(imghash)
        if not imgpath.startswith(self.cfg["img_directory"]):
            raise ValueError(f"Invalid image path {path}")
        return send_file(imgpath)

    def cleanup_cache(self):
        return delete_old_files(self.cfg["img_cache_directory"], 1)


