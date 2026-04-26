import base64
import io
import json
import os
import threading

import paho.mqtt.client as mqtt
import qrcode


def validate_homeboard_id(hb_id):
    if not isinstance(hb_id, str) or not hb_id:
        return None
    if any(c in hb_id for c in ('/', '#', '+')):
        return None
    return hb_id


def as_positive_int(v):
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


def _qr_data_url(text):
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode('ascii')


def as_bool(v):
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


class RemoteControlCore:
    """
    MQTT-based remote control for homeboard clients.

    Subscribes to homeboard state topics (bridge online/offline, displayed
    photo, slideshow active, occupancy), maintains in-memory state, and
    publishes commands back to homeboards.

    Optional callbacks fire whenever state is updated. They run on the
    paho-mqtt loop thread -- callers that do non-trivial work inside them
    (e.g. republishing to a different MQTT bus) must ensure their own
    thread-safety.

    Lifecycle: construct, then call start() to connect and begin processing
    messages. Call stop() to disconnect cleanly.
    """

    _ACTIVE_SERVER_TOPIC = "homeboard_remote_control/active_server"
    # Window after subscribing during which retained messages are treated as
    # "already claimed" rather than "new server collision".
    _ACTIVE_SERVER_CLAIM_DELAY_SECS = 2.0

    def __init__(self, mqtt_ip, mqtt_port, *,
                 public_url=None,
                 on_bridge_state=None,
                 on_displayed_photo=None,
                 on_slideshow_active=None,
                 on_occupancy=None,
                 client_id_suffix=""):
        self._broker = (mqtt_ip, int(mqtt_port))
        self._public_url = public_url
        self._on_bridge_state = on_bridge_state
        self._on_displayed_photo = on_displayed_photo
        self._on_slideshow_active = on_slideshow_active
        self._on_occupancy = on_occupancy

        self._lock = threading.Lock()
        self._homeboards = {}
        self._displayed_photos = {}
        self._slideshow_active = {}
        self._occupancy = {}

        self._active_server_settled = False
        self._active_server_claim_timer = None

        suffix = client_id_suffix or str(os.getpid())
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"homeboard_remote_control_{suffix}")
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._started = False

    def start(self):
        if self._started:
            return
        self._started = True
        ip, port = self._broker
        print(f"Connecting to homeboard MQTT broker [{ip}]:{port}...")
        self._client.connect_async(ip, port, 30)
        self._client.loop_start()

    def stop(self):
        if not self._started:
            return
        if self._active_server_claim_timer is not None:
            self._active_server_claim_timer.cancel()
            self._active_server_claim_timer = None
        self._client.loop_stop()
        self._client.disconnect()
        self._started = False

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

        client.subscribe(self._ACTIVE_SERVER_TOPIC, qos=1)
        timer = threading.Timer(self._ACTIVE_SERVER_CLAIM_DELAY_SECS,
                                self._claim_active_server_if_free)
        timer.daemon = True
        self._active_server_claim_timer = timer
        timer.start()

    def _on_message(self, _client, _ud, msg):
        if msg.topic == self._ACTIVE_SERVER_TOPIC:
            self._handle_active_server(msg)
            return
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

    def _handle_active_server(self, msg):
        try:
            data = json.loads(msg.payload.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            print(f"Non-JSON active_server message: {msg.payload!r}")
            return
        if not isinstance(data, dict):
            print(f"active_server message is not a JSON object: {data!r}")
            return
        url = data.get('url')
        # The broker echoes our own retained publish back to us; ignore it.
        if url == self._public_url:
            return
        with self._lock:
            settled = self._active_server_settled
            self._active_server_settled = True
        if not settled:
            print(f"Homeboard remote control already claimed by {url}; "
                  f"this server ({self._public_url}) will not publish a claim")
        else:
            print(f"ERROR: another homeboard remote control server announced "
                  f"itself at {url} (this server is at {self._public_url}); "
                  f"collision detected")

    def _claim_active_server_if_free(self):
        with self._lock:
            if self._active_server_settled:
                return
            self._active_server_settled = True
        if self._public_url is None:
            return
        payload = json.dumps({
            "url": self._public_url,
            "qr_img": _qr_data_url(self._public_url),
        })
        print(f"Claiming {self._ACTIVE_SERVER_TOPIC} for {self._public_url}")
        self._client.publish(self._ACTIVE_SERVER_TOPIC, payload,
                             qos=1, retain=True)

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
        if self._on_bridge_state is not None:
            self._on_bridge_state(prefix, state)

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
        if self._on_displayed_photo is not None:
            self._on_displayed_photo(prefix, data)

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
        if self._on_occupancy is not None:
            self._on_occupancy(prefix, data)

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
        if self._on_slideshow_active is not None:
            self._on_slideshow_active(prefix, active)

    def list_homeboards(self):
        with self._lock:
            return [{
                "id": k,
                "state": v,
                "slideshow_active": self._slideshow_active.get(k),
                "occupancy": self._occupancy.get(k),
                "displayed_photo": self._displayed_photos.get(k),
            } for k, v in sorted(self._homeboards.items())]

    def get_displayed_photo(self, hb_id):
        with self._lock:
            return self._displayed_photos.get(hb_id)

    def _send_cmd(self, hb_id, service, command, payload="{}"):
        hb_id = validate_homeboard_id(hb_id)
        if hb_id is None:
            return False
        topic = f"{hb_id}/cmd/{service}/{command}"
        print(f"Publishing '{topic}' ({payload}) to homeboard broker")
        info = self._client.publish(topic, payload, qos=0)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            print(f"Failed to publish '{topic}', rc={info.rc}")
            return False
        return True

    def next(self, hb_id):
        return self._send_cmd(hb_id, 'ambience', 'next')

    def prev(self, hb_id):
        return self._send_cmd(hb_id, 'ambience', 'prev')

    def force_on(self, hb_id):
        return self._send_cmd(hb_id, 'presence', 'force_on')

    def force_off(self, hb_id):
        return self._send_cmd(hb_id, 'presence', 'force_off')

    def set_transition_time_secs(self, hb_id, secs):
        secs = as_positive_int(secs)
        if secs is None:
            return False
        return self._send_cmd(hb_id, 'ambience', 'set_transition_time_secs', str(secs))

    def set_embed_qr(self, hb_id, enabled):
        enabled = as_bool(enabled)
        if enabled is None:
            return False
        return self._send_cmd(hb_id, 'photo_provider', 'set_embed_qr',
                              '1' if enabled else '0')

    def set_target_size(self, hb_id, width, height):
        width = as_positive_int(width)
        height = as_positive_int(height)
        if not width or not height:
            return False
        return self._send_cmd(hb_id, 'photo_provider', 'set_target_size',
                              f"{width}x{height}")
