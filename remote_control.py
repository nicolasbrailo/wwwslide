import json
import os
import threading

import paho.mqtt.client as mqtt
from flask import abort, request, send_from_directory


class RemoteControl:
    """
    Remote control for homeboard clients. Tracks state announced over MQTT by
    homeboards (bridge online/offline, currently displayed photo, slideshow
    active, occupancy) and publishes commands back to them.

    Homeboards are a specific kind of wwwslide client -- physical photo frames
    that listen on their own MQTT topic prefix. This is independent of the
    HTTP-registered clients tracked in clients.py.
    """

    def __init__(self, conf, flask_app):
        mqtt_ip = conf["mqtt"]["ip"]
        mqtt_port = int(conf["mqtt"]["port"])
        self._broker = (mqtt_ip, mqtt_port)

        self._lock = threading.Lock()
        self._homeboards = {}
        self._displayed_photos = {}
        self._slideshow_active = {}
        self._occupancy = {}

        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"wwwslide_remote_control_{os.getpid()}")
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        print(f"Connecting to homeboard MQTT broker [{mqtt_ip}]:{mqtt_port}...")
        self._client.connect_async(mqtt_ip, mqtt_port, 30)
        self._client.loop_start()

        flask_app.add_url_rule('/remote_control', 'remote_control_html', self._serve_html)
        flask_app.add_url_rule('/remote_control/list', 'remote_control_list', self._http_list)
        flask_app.add_url_rule('/remote_control/displayed_photo',
                               'remote_control_displayed_photo', self._http_displayed_photo)
        flask_app.add_url_rule('/remote_control/next', 'remote_control_next',
                               self._http_next, methods=['PUT'])
        flask_app.add_url_rule('/remote_control/prev', 'remote_control_prev',
                               self._http_prev, methods=['PUT'])
        flask_app.add_url_rule('/remote_control/force_on', 'remote_control_force_on',
                               self._http_force_on, methods=['PUT'])
        flask_app.add_url_rule('/remote_control/force_off', 'remote_control_force_off',
                               self._http_force_off, methods=['PUT'])
        flask_app.add_url_rule('/remote_control/set_transition_time_secs',
                               'remote_control_set_transition_time_secs',
                               self._http_set_transition_time_secs, methods=['PUT'])
        flask_app.add_url_rule('/remote_control/set_embed_qr', 'remote_control_set_embed_qr',
                               self._http_set_embed_qr, methods=['PUT'])
        flask_app.add_url_rule('/remote_control/set_target_size',
                               'remote_control_set_target_size',
                               self._http_set_target_size, methods=['PUT'])

    def stop(self):
        self._client.loop_stop()
        self._client.disconnect()

    def _serve_html(self):
        return send_from_directory('html', 'remote_control.html')

    def _on_connect(self, client, _ud, _flags, ret_code, _props):
        if ret_code == 0:
            print(f"Connected to homeboard MQTT broker {self._broker}")
        else:
            print(f"Homeboard MQTT connect to {self._broker} returned rc={ret_code}")
        # Bridges publish "<prefix>/state/bridge" as retained "online"/"offline".
        # Subscribing to this wildcard lets us enumerate all registered prefixes.
        client.subscribe('+/state/bridge', qos=0)
        client.subscribe('+/state/displayed_photo', qos=0)
        client.subscribe('+/state/slideshow_active', qos=0)
        client.subscribe('+/state/occupancy', qos=0)

    def _on_message(self, _client, _ud, msg):
        parts = msg.topic.split('/')
        if len(parts) != 3 or parts[1] != 'state':
            return
        prefix = parts[0]
        suffix = parts[2]
        if suffix == 'bridge':
            self._handle_bridge_state(prefix, msg.payload)
        elif suffix == 'displayed_photo':
            self._handle_displayed_photo(prefix, msg.payload)
        elif suffix == 'slideshow_active':
            self._handle_slideshow_active(prefix, msg.payload)
        elif suffix == 'occupancy':
            self._handle_occupancy(prefix, msg.payload)

    def _handle_bridge_state(self, prefix, raw_payload):
        try:
            state = raw_payload.decode('utf-8').strip().strip('"').lower()
        except UnicodeDecodeError:
            print(f"Non-utf8 bridge state for '{prefix}'")
            return
        if state not in ('online', 'offline'):
            print(f"Unexpected bridge state '{state}' for '{prefix}'")
            return
        with self._lock:
            prev = self._homeboards.get(prefix)
            self._homeboards[prefix] = state
        if prev != state:
            print(f"Homeboard '{prefix}' is {state}")

    def _handle_displayed_photo(self, prefix, raw_payload):
        try:
            data = json.loads(raw_payload.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            print(f"Non-JSON displayed_photo for '{prefix}'")
            return
        if not isinstance(data, dict):
            print(f"displayed_photo for '{prefix}' is not a JSON object")
            return
        with self._lock:
            self._displayed_photos[prefix] = data
        print(f"Homeboard '{prefix}' displaying: {data.get('filename')}")

    def _handle_occupancy(self, prefix, raw_payload):
        try:
            data = json.loads(raw_payload.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            print(f"Non-JSON occupancy for '{prefix}'")
            return
        if not isinstance(data, dict):
            print(f"occupancy for '{prefix}' is not a JSON object")
            return
        with self._lock:
            self._occupancy[prefix] = data

    def _handle_slideshow_active(self, prefix, raw_payload):
        try:
            text = raw_payload.decode('utf-8').strip().strip('"').lower()
        except UnicodeDecodeError:
            print(f"Non-utf8 slideshow_active for '{prefix}'")
            return
        if text in ('1', 'true', 'on', 'active', 'yes'):
            active = True
        elif text in ('0', 'false', 'off', 'inactive', 'no'):
            active = False
        else:
            print(f"Unknown slideshow_active value '{text}' for '{prefix}'")
            return
        with self._lock:
            prev = self._slideshow_active.get(prefix)
            self._slideshow_active[prefix] = active
        if prev != active:
            print(f"Homeboard '{prefix}' slideshow {'active' if active else 'inactive'}")

    def _http_list(self):
        with self._lock:
            items = [{
                "id": k,
                "state": v,
                "slideshow_active": self._slideshow_active.get(k),
                "occupancy": self._occupancy.get(k),
                "displayed_photo": self._displayed_photos.get(k),
            } for k, v in sorted(self._homeboards.items())]
        return {"homeboards": items}

    def _http_displayed_photo(self):
        hb_id = self._validate_homeboard_id(request.args.get('homeboard_id'))
        if hb_id is None:
            return abort(400, description="Missing or invalid homeboard_id")
        with self._lock:
            photo = self._displayed_photos.get(hb_id)
        return {"displayed_photo": photo}

    @staticmethod
    def _validate_homeboard_id(hb_id):
        if not isinstance(hb_id, str) or not hb_id:
            return None
        if any(c in hb_id for c in ('/', '#', '+')):
            return None
        return hb_id

    def _send_cmd(self, homeboard_id, service, command, payload="{}"):
        topic = f"{homeboard_id}/cmd/{service}/{command}"
        print(f"Publishing '{topic}' ({payload}) to homeboard broker")
        info = self._client.publish(topic, payload, qos=0)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            print(f"Failed to publish '{topic}', rc={info.rc}")

    def _read_json_body(self):
        try:
            payload = request.get_json(force=True)
        except Exception:
            return abort(400, description="Invalid JSON body")
        if not isinstance(payload, dict):
            return abort(400, description="Body must be a JSON object")
        return payload

    def _read_hb_id_from_body(self):
        body = self._read_json_body()
        hb_id = self._validate_homeboard_id(body.get('homeboard_id'))
        if hb_id is None:
            return abort(400, description="Missing or invalid homeboard_id")
        return body, hb_id

    @staticmethod
    def _as_positive_int(v):
        if isinstance(v, bool):
            return None
        if isinstance(v, int) and v >= 0:
            return v
        if isinstance(v, str):
            try:
                n = int(v)
                return n if n >= 0 else None
            except ValueError:
                return None
        return None

    @staticmethod
    def _as_bool(v):
        if isinstance(v, bool):
            return v
        if isinstance(v, int) and v in (0, 1):
            return bool(v)
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ('1', 'true', 'yes', 'on'):
                return True
            if s in ('0', 'false', 'no', 'off'):
                return False
        return None

    def _http_next(self):
        _, hb_id = self._read_hb_id_from_body()
        self._send_cmd(hb_id, 'ambience', 'next')
        return {}

    def _http_prev(self):
        _, hb_id = self._read_hb_id_from_body()
        self._send_cmd(hb_id, 'ambience', 'prev')
        return {}

    def _http_force_on(self):
        _, hb_id = self._read_hb_id_from_body()
        self._send_cmd(hb_id, 'ambience', 'force_on')
        return {}

    def _http_force_off(self):
        _, hb_id = self._read_hb_id_from_body()
        self._send_cmd(hb_id, 'ambience', 'force_off')
        return {}

    def _http_set_transition_time_secs(self):
        body, hb_id = self._read_hb_id_from_body()
        secs = self._as_positive_int(body.get('secs'))
        if secs is None:
            return abort(400, description="Missing or invalid 'secs' (non-negative integer)")
        self._send_cmd(hb_id, 'ambience', 'set_transition_time_secs', str(secs))
        return {}

    def _http_set_embed_qr(self):
        body, hb_id = self._read_hb_id_from_body()
        enabled = self._as_bool(body.get('enabled'))
        if enabled is None:
            return abort(400, description="Missing or invalid 'enabled' (bool)")
        self._send_cmd(hb_id, 'photo_provider', 'set_embed_qr', '1' if enabled else '0')
        return {}

    def _http_set_target_size(self):
        body, hb_id = self._read_hb_id_from_body()
        width = self._as_positive_int(body.get('width'))
        height = self._as_positive_int(body.get('height'))
        if width is None or width == 0 or height is None or height == 0:
            return abort(400, description="Missing or invalid 'width'/'height' (positive integers)")
        self._send_cmd(hb_id, 'photo_provider', 'set_target_size', f"{width}x{height}")
        return {}
