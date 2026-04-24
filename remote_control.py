from flask import abort, request, send_from_directory

from homeboard_remote_control import (
    RemoteControlCore,
    validate_homeboard_id,
    as_positive_int,
    as_bool,
)


class RemoteControl:
    """
    Flask HTTP adapter for homeboard_remote_control.RemoteControlCore.
    Registers /remote_control/* endpoints and serves the UI at /remote_control.
    """

    def __init__(self, conf, flask_app):
        self._core = RemoteControlCore(
            conf["mqtt"]["ip"],
            int(conf["mqtt"]["port"]),
        )
        self._core.start()

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
        self._core.stop()

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
