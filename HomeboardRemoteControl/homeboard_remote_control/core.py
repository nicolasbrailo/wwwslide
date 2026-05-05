import base64
import io
import json
import logging
import os
import threading

import paho.mqtt.client as mqtt
import qrcode

log = logging.getLogger(__name__)


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
                 on_host_info=None,
                 client_id_suffix=""):
        self._broker = (mqtt_ip, int(mqtt_port))
        self._public_url = public_url
        self._on_bridge_state = on_bridge_state
        self._on_displayed_photo = on_displayed_photo
        self._on_slideshow_active = on_slideshow_active
        self._on_occupancy = on_occupancy
        self._on_host_info = on_host_info

        self._lock = threading.Lock()
        self._homeboards = {}
        self._displayed_photos = {}
        self._slideshow_active = {}
        self._occupancy = {}
        self._host_info = {}

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
        log.info("Connecting to homeboard MQTT broker [%s]:%s...", ip, port)
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
            log.info("Connected to homeboard MQTT broker %s", self._broker)
        else:
            log.warning("Homeboard MQTT connect to %s returned rc=%s", self._broker, ret_code)
        # Bridges publish "<prefix>/state/bridge" retained, carrying both the
        # online/offline state and the host info (machine_id, hostname, ip,
        # ...) in a single JSON object. Subscribing to this wildcard lets us
        # enumerate all registered prefixes.
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
            self._handle_bridge(prefix, msg.payload)
        elif suffix == 'displayed_photo':
            self._handle_displayed_photo(prefix, msg.payload)
        elif suffix == 'slideshow_active':
            self._handle_slideshow_active(prefix, msg.payload)
        elif suffix == 'occupancy':
            self._handle_occupancy(prefix, msg.payload)

    def _handle_active_server(self, msg):
        if self._public_url:
            # We're not an active RC server, so we don't care about collisions
            return
        try:
            data = json.loads(msg.payload.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            log.warning("Non-JSON active_server message: %r", msg.payload)
            return
        if not isinstance(data, dict):
            log.warning("active_server message is not a JSON object: %r", data)
            return
        url = data.get('url')
        # The broker echoes our own retained publish back to us; ignore it.
        if url == self._public_url:
            return
        with self._lock:
            settled = self._active_server_settled
            self._active_server_settled = True
        if not settled:
            log.info("Homeboard remote control already claimed by %s; "
                     "this server (%s) will not publish a claim",
                     url, self._public_url)
        else:
            log.error("Another homeboard remote control server announced "
                      "itself at %s (this server is at %s); collision detected",
                      url, self._public_url)

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
        log.info("Claiming %s for %s",
                 self._ACTIVE_SERVER_TOPIC, self._public_url)
        self._client.publish(self._ACTIVE_SERVER_TOPIC, payload,
                             qos=1, retain=True)

    def _handle_bridge(self, prefix, raw_payload):
        try:
            data = json.loads(raw_payload.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            log.warning("Non-JSON bridge state for '%s': %r", prefix, raw_payload)
            return
        if not isinstance(data, dict):
            log.warning("bridge state for '%s' is not a JSON object", prefix)
            return
        state = data.get('state')
        if state not in ('online', 'offline'):
            log.warning("Unexpected bridge state %r for '%s'", state, prefix)
            return
        with self._lock:
            prev = self._homeboards.get(prefix)
            self._homeboards[prefix] = state
            self._host_info[prefix] = data
        if prev != state:
            log.info("Homeboard '%s' is %s", prefix, state)
        if self._on_bridge_state is not None:
            self._on_bridge_state(prefix, state)
        if self._on_host_info is not None:
            self._on_host_info(prefix, data)

    def _handle_displayed_photo(self, prefix, raw_payload):
        try:
            data = json.loads(raw_payload.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            log.warning("Non-JSON displayed_photo for '%s'", prefix)
            return
        if not isinstance(data, dict):
            log.warning("displayed_photo for '%s' is not a JSON object", prefix)
            return
        with self._lock:
            self._displayed_photos[prefix] = data
        log.info("Homeboard '%s' displaying: %s", prefix, data.get('filename'))
        if self._on_displayed_photo is not None:
            self._on_displayed_photo(prefix, data)

    def _handle_occupancy(self, prefix, raw_payload):
        try:
            data = json.loads(raw_payload.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            log.warning("Non-JSON occupancy for '%s'", prefix)
            return
        if not isinstance(data, dict):
            log.warning("occupancy for '%s' is not a JSON object", prefix)
            return
        with self._lock:
            self._occupancy[prefix] = data
        if self._on_occupancy is not None:
            self._on_occupancy(prefix, data)

    def _handle_slideshow_active(self, prefix, raw_payload):
        try:
            data = json.loads(raw_payload.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            log.warning("Non-JSON slideshow_active for '%s': %r", prefix, raw_payload)
            return
        if not isinstance(data, dict):
            log.warning("slideshow_active for '%s' is not a JSON object", prefix)
            return
        active = data.get('active')
        if not isinstance(active, bool):
            log.warning("slideshow_active 'active' field for '%s' is not a bool: %r",
                        prefix, active)
            return
        with self._lock:
            prev = self._slideshow_active.get(prefix)
            self._slideshow_active[prefix] = active
        if prev != active:
            log.info("Homeboard '%s' slideshow %s",
                     prefix, 'active' if active else 'inactive')
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
                "host_info": self._host_info.get(k),
            } for k, v in sorted(self._homeboards.items())]

    def get_displayed_photo(self, hb_id):
        with self._lock:
            return self._displayed_photos.get(hb_id)

    def _send_cmd(self, hb_id, service, command, payload="{}"):
        hb_id = validate_homeboard_id(hb_id)
        if hb_id is None:
            return False
        topic = f"{hb_id}/cmd/{service}/{command}"
        log_payload = payload if len(payload) <= 50 else payload[:50] + "..."
        log.info("Publishing '%s' (%s) to homeboard broker", topic, log_payload)
        info = self._client.publish(topic, payload, qos=0)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            log.error("Failed to publish '%s', rc=%s", topic, info.rc)
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
        return self._send_cmd(hb_id, 'ambience', 'set_transition_time_secs',
                              json.dumps({"secs": secs}))

    def announce(self, hb_id, timeout_secs, msg):
        timeout_secs = as_positive_int(timeout_secs)
        if timeout_secs is None:
            return False
        if not isinstance(msg, str):
            return False
        return self._send_cmd(hb_id, 'ambience', 'announce',
                              json.dumps({"timeout": timeout_secs, "msg": msg}))

    def set_svg_overlay(self, hb_id, timeout_secs, svg):
        timeout_secs = as_positive_int(timeout_secs)
        if timeout_secs is None:
            return False
        if not isinstance(svg, str):
            return False
        return self._send_cmd(hb_id, 'ambience', 'set_svg_overlay',
                              json.dumps({"timeout": timeout_secs, "svg": svg}))

    def set_embed_qr(self, hb_id, enabled):
        enabled = as_bool(enabled)
        if enabled is None:
            return False
        return self._send_cmd(hb_id, 'photo_provider', 'set_embed_qr',
                              json.dumps({"on": enabled}))

    def set_target_size(self, hb_id, width, height):
        width = as_positive_int(width)
        height = as_positive_int(height)
        if not width or not height:
            return False
        return self._send_cmd(hb_id, 'photo_provider', 'set_target_size',
                              json.dumps({"w": width, "h": height}))

    _RENDER_ROTATIONS = (0, 90, 180, 270)
    _RENDER_INTERPS = ('nearest', 'bilinear')
    _RENDER_H_ALIGNS = ('left', 'center', 'right')
    _RENDER_V_ALIGNS = ('top', 'center', 'bottom')

    def set_render_config(self, hb_id, rotation, interp, h_align, v_align):
        rot = as_positive_int(rotation)
        if rot is None or rot not in self._RENDER_ROTATIONS:
            return False
        if interp not in self._RENDER_INTERPS:
            return False
        if h_align not in self._RENDER_H_ALIGNS:
            return False
        if v_align not in self._RENDER_V_ALIGNS:
            return False
        return self._send_cmd(hb_id, 'ambience', 'set_render_config',
                              json.dumps({
                                  "rotation": rot,
                                  "interp": interp,
                                  "h_align": h_align,
                                  "v_align": v_align,
                              }))
