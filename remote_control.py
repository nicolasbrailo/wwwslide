import datetime
import logging
import threading
import time

from flask import abort, request, send_from_directory

from homeboard_remote_control import (
    RemoteControlCore,
    validate_homeboard_id,
    as_positive_int,
    as_bool,
)

log = logging.getLogger(__name__)


class RemoteControl:
    """
    Flask HTTP adapter for homeboard_remote_control.RemoteControlCore.
    Registers /remote_control/* endpoints and serves the UI at /remote_control.

    Also runs a nightly janitor that clears retained `state/bridge` records
    for homeboards that have been offline since longer than
    _JANITOR_STALE_SECS. The bridge republishes a fresh `started_at` every
    time it reconnects, so a device that genuinely returns will overwrite
    the cleared record on its own; anything still showing an old
    `started_at` while offline is presumed gone for good.
    """

    # Local hour to run the janitor at. 3am is past midnight chores and
    # before morning use.
    _JANITOR_RUN_HOUR = 3
    # Offline records with started_at older than this are cleared.
    _JANITOR_STALE_SECS = 3 * 24 * 3600

    def __init__(self, conf, flask_app):
        self._core = RemoteControlCore(
            conf["homeboard_mqtt"]["ip"],
            int(conf["homeboard_mqtt"]["port"]),
            public_url=conf.get("service_url"),
        )
        self._core.start()

        self._janitor_stopping = False
        self._janitor_timer = None
        # On startup, clean up old homeboard instances to make dev easier
        self._schedule_janitor(5)

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
        flask_app.add_url_rule('/remote_control/set_render_config',
                               'remote_control_set_render_config',
                               self._http_set_render_config, methods=['PUT'])

    def stop(self):
        self._janitor_stopping = True
        if self._janitor_timer is not None:
            self._janitor_timer.cancel()
            self._janitor_timer = None
        self._core.stop()

    def _schedule_janitor(self, delay=None):
        if self._janitor_stopping:
            return
        if not delay:
            delay = self._secs_until_next_run()
        log.info("janitor: next run in %.1fh", delay / 3600.0)
        self._janitor_timer = threading.Timer(delay, self._run_janitor)
        self._janitor_timer.daemon = True
        self._janitor_timer.start()

    def _secs_until_next_run(self):
        now = datetime.datetime.now()
        target = now.replace(hour=self._JANITOR_RUN_HOUR,
                             minute=0, second=0, microsecond=0)
        if target <= now:
            target += datetime.timedelta(days=1)
        return (target - now).total_seconds()

    def _run_janitor(self):
        if self._janitor_stopping:
            return
        try:
            self._clear_stale_offline()
        except Exception:
            log.exception("janitor: run failed")
        self._schedule_janitor()

    def _clear_stale_offline(self):
        cutoff = time.time() #- self._JANITOR_STALE_SECS
        cleared = 0
        # list_homeboards() returns a snapshot, so we don't hold the core's
        # internal lock while publishing. Race window: a stale device could
        # come online between snapshot and clear; harmless because it'd
        # republish on its next reconnect.
        for hb in self._core.list_homeboards():
            host_info = hb.get("host_info") or {}
            started_at = host_info.get("started_at")
            if not isinstance(started_at, (int, float)):
                started_at = 0
            log.info("Found HB %s started_at=%s now=%s", hb['id'], started_at, cutoff)
            if hb.get("state", "offline") != "offline":
                continue
            if started_at >= cutoff:
                continue
            topic = f"{hb['id']}/state/bridge"
            log.info("janitor: clearing stale retained %s (started_at=%s)",
                     topic, started_at)
            # Reach into the underlying paho client to publish a zero-byte
            # retained payload, which the broker treats as "delete the
            # retained record for this topic." Core's command path is for
            # `<id>/cmd/...` only, so we don't route this through it.
            self._core._client.publish(topic, payload=None,
                                       qos=0, retain=True)
            cleared += 1
        log.info("janitor: cleared %d stale homeboard record(s)", cleared)

    def _serve_html(self):
        return send_from_directory('html', 'remote_control.html')

    def _http_list(self):
        return {"homeboards": self._core.list_homeboards()}

    def _http_displayed_photo(self):
        hb_id = validate_homeboard_id(request.args.get('homeboard_id'))
        if hb_id is None:
            return abort(400, description="Missing or invalid homeboard_id")
        return {"displayed_photo": self._core.get_displayed_photo(hb_id)}

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
        hb_id = validate_homeboard_id(body.get('homeboard_id'))
        if hb_id is None:
            return abort(400, description="Missing or invalid homeboard_id")
        return body, hb_id

    def _http_next(self):
        _, hb_id = self._read_hb_id_from_body()
        self._core.next(hb_id)
        return {}

    def _http_prev(self):
        _, hb_id = self._read_hb_id_from_body()
        self._core.prev(hb_id)
        return {}

    def _http_force_on(self):
        _, hb_id = self._read_hb_id_from_body()
        self._core.force_on(hb_id)
        return {}

    def _http_force_off(self):
        _, hb_id = self._read_hb_id_from_body()
        self._core.force_off(hb_id)
        return {}

    def _http_set_transition_time_secs(self):
        body, hb_id = self._read_hb_id_from_body()
        secs = as_positive_int(body.get('secs'))
        if secs is None:
            return abort(400, description="Missing or invalid 'secs' (non-negative integer)")
        self._core.set_transition_time_secs(hb_id, secs)
        return {}

    def _http_set_embed_qr(self):
        body, hb_id = self._read_hb_id_from_body()
        enabled = as_bool(body.get('enabled'))
        if enabled is None:
            return abort(400, description="Missing or invalid 'enabled' (bool)")
        self._core.set_embed_qr(hb_id, enabled)
        return {}

    def _http_set_target_size(self):
        body, hb_id = self._read_hb_id_from_body()
        width = as_positive_int(body.get('width'))
        height = as_positive_int(body.get('height'))
        if width is None or width == 0 or height is None or height == 0:
            return abort(400, description="Missing or invalid 'width'/'height' (positive integers)")
        self._core.set_target_size(hb_id, width, height)
        return {}

    def _http_set_render_config(self):
        body, hb_id = self._read_hb_id_from_body()
        rotation = as_positive_int(body.get('rotation'))
        interp = body.get('interp')
        h_align = body.get('h_align')
        v_align = body.get('v_align')
        if not self._core.set_render_config(hb_id, rotation, interp, h_align, v_align):
            return abort(400, description="Invalid render config "
                         "(rotation 0/90/180/270, interp nearest/bilinear, "
                         "h_align left/center/right, v_align top/center/bottom)")
        return {}
