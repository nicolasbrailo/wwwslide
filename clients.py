from flask import request
from image_sender import img_path_from_hash, get_img_meta
import json
import time
import os

class Clients:
    """
    Manage multiple clients of the slide service. Note there is no real attempt at security, this service is thought for LAN use only: client IDs are trivial to
    guess, there is no attempt to authenticate them, and a client can easily interfere with another's settings if it wishes to do so.
    """

    def __init__(self, conf, flask_app, albums, img_sender):
        self.image_queue_size = conf["image_queue_size"]
        self.max_images_per_album = conf["max_images_per_album"]
        if self.max_images_per_album > self.image_queue_size:
            raise ValueError(f"Max album size of {self.max_images_per_album} is more than image queue size of {self.image_queue_size}")

        self.embed_info_qr_code_default = conf["embed_info_qr_code_default"]
        self.default_target_width = int(conf["default_target_width"])
        self.default_target_height = int(conf["default_target_height"])
        self.img_directory = conf["img_directory"]

        self.albums = albums
        self.img_sender = img_sender
        self.known_clients = {}

        flask_app.add_url_rule("/client_ls", "client_ls", self.client_ls)
        flask_app.add_url_rule("/client_ls_txt", "client_ls_txt", self.client_ls_txt)
        flask_app.add_url_rule("/client_register", "client_register", self.client_register)
        flask_app.add_url_rule("/client_info", "client_info", self.client_info)
        flask_app.add_url_rule("/client_info/<client_id>", "client_info", self.client_info)

        flask_app.add_url_rule("/client_cfg/embed_info_qr_code/<v>", "client_cfg_embed_info_qr_code", self.client_cfg_embed_info_qr_code)
        flask_app.add_url_rule("/client_cfg/<client_id>/embed_info_qr_code/<v>", "client_cfg_embed_info_qr_code", self.client_cfg_embed_info_qr_code)
        flask_app.add_url_rule("/client_cfg/target_size/<width>x<height>", "client_cfg_target_size", self.client_cfg_target_size)
        flask_app.add_url_rule("/client_cfg/<client_id>/target_size/<width>x<height>", "client_cfg_target_size", self.client_cfg_target_size)
        flask_app.add_url_rule("/client_cfg//target_size/default", "client_cfg_target_size_default", self.client_cfg_target_size_default)
        flask_app.add_url_rule("/client_cfg/<client_id>/target_size/default", "client_cfg_target_size_default", self.client_cfg_target_size_default)
        flask_app.add_url_rule("/client_cfg//target_size/no_resize", "client_cfg_target_size_no_resize", self.client_cfg_target_size_no_resize)
        flask_app.add_url_rule("/client_cfg/<client_id>/target_size/no_resize", "client_cfg_target_size_no_resize", self.client_cfg_target_size_no_resize)

        flask_app.add_url_rule("/get_image", "get_image", self.get_next_img)
        flask_app.add_url_rule("/get_next_img", "get_next_img", self.get_next_img)
        flask_app.add_url_rule("/get_next_img/<client_id>", "get_next_img", self.get_next_img)
        flask_app.add_url_rule("/get_prev_img", "get_prev_img", self.get_prev_img)
        flask_app.add_url_rule("/get_prev_img/<client_id>", "get_prev_img", self.get_prev_img)
        flask_app.add_url_rule("/get_current_img_meta", "get_current_img_meta", self.get_current_img_meta)
        flask_app.add_url_rule("/get_current_img_meta/<client_id>", "get_current_img_meta", self.get_current_img_meta)
        flask_app.add_url_rule("/reset_album", "reset_album", self.reset_album)
        flask_app.add_url_rule("/reset_album/<client_id>", "reset_album", self.reset_album)
        flask_app.add_url_rule("/show_full_album", "show_full_album", self.show_full_album)
        flask_app.add_url_rule("/show_full_album/<client_id>", "show_full_album", self.show_full_album)
        flask_app.add_url_rule("/show_full_album@<path:imghash>", "show_full_album", self.show_full_album)
        flask_app.add_url_rule("/show_full_album/<client_id>@<path:imghash>", "show_full_album", self.show_full_album)


    def _guess_or_register_client(self, client_id=None):
        if client_id is not None:
            if client_id in self.known_clients:
                return self.known_clients[client_id]["client_id"]
            else:
                # Register a new client with requested id
                return self._client_register_impl(client_id)

        # client id not specified, see if we know client by ip
        for client_id,cfg in self.known_clients.items():
            if cfg["ip"] == request.remote_addr:
                return cfg["client_id"]

        # Unknown client, register a new one and assign id
        return self.client_register()


    def client_ls(self):
        return json.dumps(self.known_clients, indent=4)

    def client_ls_txt(self):
        return '<pre>' + json.dumps(self.known_clients, indent=4)


    def client_register(self):
        return self._client_register_impl(None)

    def _client_register_impl(self, new_id=None):
        if new_id is None:
            new_id = f"client_{int(time.time())}{len(self.known_clients)}"
        self.known_clients[new_id] = {
                "ip": request.remote_addr,
                "client_id": new_id,
                "embed_info_qr_code": self.embed_info_qr_code_default,
                "target_width": int(self.default_target_width),
                "target_height": int(self.default_target_height),
                "active_album": None,
                "imgs_queue": [],
                "imgs_queue_idx": 0,
                "last_seen": time.time(),
            }
        return new_id


    def client_cfg_embed_info_qr_code(self, client_id=None, v=None):
        if v is None or v.lower() in ["default"]:
            v = self.embed_info_qr_code_default
        elif v.lower() in [0, "0", "no", "off", "false"]:
            v = False
        elif v.lower() in [1, "1", "yes", "on", "true"]:
            v = True
        else:
            return f"Invalid bool-like {v}", 400
        client_id = self._guess_or_register_client(client_id)
        self.known_clients[client_id]["embed_info_qr_code"] = v
        return self.client_info(client_id)


    def client_cfg_target_size(self, client_id=None, width=None, height=None):
        client_id = self._guess_or_register_client(client_id)
        if width is None or height is None or not width.isdigit() or not height.isdigit():
            return f"Expected size in WxH pixels format. W and H must be integers"
        self.known_clients[client_id]["target_width"] = int(width)
        self.known_clients[client_id]["target_height"] = int(height)
        return self.client_info(client_id)

    def client_cfg_target_size_default(self, client_id=None):
        client_id = self._guess_or_register_client(client_id)
        self.known_clients[client_id]["target_width"] = int(self.default_target_width)
        self.known_clients[client_id]["target_height"] = int(self.default_target_height)
        return self.client_info(client_id)

    def client_cfg_target_size_no_resize(self, client_id=None):
        client_id = self._guess_or_register_client(client_id)
        self.known_clients[client_id]["target_width"] = None
        self.known_clients[client_id]["target_height"] = None
        return self.client_info(client_id)


    def client_info(self, client_id=None):
        client_id = self._guess_or_register_client(client_id)
        if client_id is not None:
            return json.dumps(self.known_clients[client_id])
        return json.dumps(None)


    def reset_album(self, client_id=None):
        client_id = self._guess_or_register_client(client_id)
        cfg = self.known_clients[client_id]
        del cfg["imgs_queue"][cfg["imgs_queue_idx"]+1:]
        return self.get_next_img(client_id)


    def show_full_album(self, client_id=None, imghash=None):
        client_id = self._guess_or_register_client(client_id)
        cfg = self.known_clients[client_id]

        if imghash is not None:
            imgpath = img_path_from_hash(imghash)
        else:
            imgpath = cfg["imgs_queue"][cfg["imgs_queue_idx"]]

        if not imgpath.startswith(self.img_directory):
            raise ValueError(f"Invalid image path {imgpath}")

        # Remove images after current one
        del cfg["imgs_queue"][cfg["imgs_queue_idx"]+1:]

        album = get_img_meta(self.img_directory, imgpath, None)['albumpath']
        cfg["active_album"] = album
        # No remove if history bigger than max; user requested full album
        new_imgs = self.albums.random_select_pictures(cfg["active_album"], None)
        cfg["imgs_queue"].extend(new_imgs)
        return f"Loaded {len(new_imgs)} images"


    def get_next_img(self, client_id=None):
        client_id = self._guess_or_register_client(client_id)
        cfg = self.known_clients[client_id]
        if cfg["imgs_queue_idx"] + 1 >= len(cfg["imgs_queue"]):
            cfg["active_album"] = self.albums.get_random()
            new_imgs = self.albums.random_select_pictures(cfg["active_album"], self.max_images_per_album)
            cfg["imgs_queue"].extend(new_imgs)
            cnt_to_rm = len(cfg["imgs_queue"]) - self.image_queue_size
            if cnt_to_rm > 0:
                del cfg["imgs_queue"][0:cnt_to_rm-1]
            cfg["imgs_queue_idx"] = len(cfg["imgs_queue"]) - len(new_imgs)
        else:
            cfg["imgs_queue_idx"] += 1
        return self._send_img(client_id, cfg["imgs_queue"][cfg["imgs_queue_idx"]])


    def get_prev_img(self, client_id=None):
        client_id = self._guess_or_register_client(client_id)
        cfg = self.known_clients[client_id]

        if len(cfg["imgs_queue"]) == 0:
            # There is no history
            return self.get_next_img(client_id)

        if cfg["imgs_queue_idx"] == 0:
            # Reached beginning of history
            return self._send_img(client_id, cfg["imgs_queue"][cfg["imgs_queue_idx"]])

        cfg["imgs_queue_idx"] -= 1
        return self._send_img(client_id, cfg["imgs_queue"][cfg["imgs_queue_idx"]])


    def get_current_img_meta(self, client_id=None):
        client_id = self._guess_or_register_client(client_id)
        cfg = self.known_clients[client_id]

        if len(cfg["imgs_queue"]) == 0:
            return json.dumps(None)

        img = cfg["imgs_queue"][cfg["imgs_queue_idx"]]
        return self.img_sender.get_image_meta(img)


    def _send_img(self, client_id, img):
        self.known_clients[client_id]["last_seen"] = time.time()
        return self.img_sender.send_image(self.known_clients[client_id], img)

