// Remote control UI for homeboards. Polls /remote_control/list and renders a
// card per homeboard with action buttons and a small config form.

const POLL_MS = 5000;

function putJson(url, body, onDone) {
  mAjax({
    type: 'put',
    url: url,
    data: JSON.stringify(body),
    dataType: 'json',
    success: _ => { if (onDone) onDone(null); refresh(); },
    error: err => { if (onDone) onDone(err); setStatus(`Error: ${url} -> ${err.status}`); },
  });
}

function setStatus(msg) {
  m$('status').textContent = msg;
}

function esc(s) {
  if (s === null || s === undefined) return '';
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function isLatLon(v) {
  return v && typeof v === 'object'
    && typeof v.lat === 'number' && typeof v.lon === 'number';
}

function renderValue(k, v) {
  if (k === 'src_url' && typeof v === 'string') {
    return `<a href="${esc(v)}" target="_blank" rel="noopener">${esc(v)}</a>`;
  }
  if (isLatLon(v)) {
    const url = `https://www.openstreetmap.org/?mlat=${v.lat}&mlon=${v.lon}&zoom=15`;
    return `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(v.lat)}, ${esc(v.lon)}</a>`;
  }
  if (v !== null && typeof v === 'object') return esc(JSON.stringify(v));
  return esc(String(v));
}

function renderKv(obj) {
  if (!obj || typeof obj !== 'object') return '<em>(none)</em>';
  const keys = Object.keys(obj);
  if (keys.length === 0) return '<em>(empty)</em>';
  const rows = keys.map(k =>
    `<tr><th>${esc(k)}</th><td>${renderValue(k, obj[k])}</td></tr>`
  ).join('');
  return `<table class="kv">${rows}</table>`;
}

function renderCard(hb) {
  const stateCls = hb.state === 'online' ? 'online' : 'offline';
  const slideshow = hb.slideshow_active === null || hb.slideshow_active === undefined
    ? 'unknown' : (hb.slideshow_active ? 'active' : 'inactive');
  return `
    <div class="hb_card" data-hb-id="${esc(hb.id)}">
      <h3>${esc(hb.id)}</h3>
      <div class="hb_state">
        bridge: <span class="${stateCls}">${esc(hb.state)}</span>
        &middot; slideshow: ${esc(slideshow)}
      </div>
      <div class="hb_meta">
        <div class="hb_meta_col"><h4>displayed photo</h4>${renderKv(hb.displayed_photo)}</div>
        <div class="hb_meta_col"><h4>occupancy</h4>${renderKv(hb.occupancy)}</div>
      </div>
      <div class="hb_controls">
        <button data-act="prev">⏪ prev</button>
        <button data-act="next">⏩ next</button>
        <button data-act="force_on">force on</button>
        <button data-act="force_off">force off</button>
      </div>
      <div class="hb_config">
        <label>transition (s):
          <input type="text" data-cfg="secs" value="">
          <button data-act="set_transition_time_secs">set</button>
        </label>
        <label>target size:
          <input type="text" data-cfg="width" value="" placeholder="w">x
          <input type="text" data-cfg="height" value="" placeholder="h">
          <button data-act="set_target_size">set</button>
        </label>
        <label>embed QR:
          <button data-act="set_embed_qr" data-val="1">on</button>
          <button data-act="set_embed_qr" data-val="0">off</button>
        </label>
        <label>render:
          <select data-cfg="rotation">
            <option value="0">0&deg;</option>
            <option value="90">90&deg;</option>
            <option value="180">180&deg;</option>
            <option value="270">270&deg;</option>
          </select>
          <select data-cfg="interp">
            <option value="bilinear">bilinear</option>
            <option value="nearest">nearest</option>
          </select>
          <select data-cfg="h_align">
            <option value="center">center</option>
            <option value="left">left</option>
            <option value="right">right</option>
          </select>
          <select data-cfg="v_align">
            <option value="center">center</option>
            <option value="top">top</option>
            <option value="bottom">bottom</option>
          </select>
          <button data-act="set_render_config">set</button>
        </label>
      </div>
    </div>
  `;
}

function wireCard(cardEl) {
  const hbId = cardEl.getAttribute('data-hb-id');
  const getCfg = name => {
    const el = cardEl.querySelector(`[data-cfg="${name}"]`);
    return el ? el.value.trim() : '';
  };

  cardEl.querySelectorAll('button[data-act]').forEach(btn => {
    btn.addEventListener('click', () => {
      const act = btn.getAttribute('data-act');
      const body = { homeboard_id: hbId };
      if (act === 'set_transition_time_secs') {
        const secs = getCfg('secs');
        if (!secs) return setStatus("Enter transition seconds first");
        body.secs = secs;
      } else if (act === 'set_target_size') {
        const w = getCfg('width'), h = getCfg('height');
        if (!w || !h) return setStatus("Enter width and height first");
        body.width = w;
        body.height = h;
      } else if (act === 'set_embed_qr') {
        body.enabled = btn.getAttribute('data-val');
      } else if (act === 'set_render_config') {
        body.rotation = getCfg('rotation');
        body.interp = getCfg('interp');
        body.h_align = getCfg('h_align');
        body.v_align = getCfg('v_align');
      }
      putJson(`/remote_control/${act}`, body);
    });
  });
}

function refresh() {
  mAjax({
    url: '/remote_control/list',
    dataType: 'json',
    success: resp => {
      const list = (resp && resp.homeboards) || [];
      const container = m$('hb_list');
      if (list.length === 0) {
        container.innerHTML = '<p>No homeboards seen yet.</p>';
      } else {
        container.innerHTML = list.map(renderCard).join('');
        container.querySelectorAll('.hb_card').forEach(wireCard);
      }
      setStatus(`${list.length} homeboard(s) · updated ${new Date().toLocaleTimeString()}`);
    },
    error: err => setStatus(`Error loading list: ${err.status} ${err.statusText || ''}`),
  });
}

refresh();
setInterval(refresh, POLL_MS);
