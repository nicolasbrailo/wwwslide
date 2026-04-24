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

function renderCard(hb) {
  const stateCls = hb.state === 'online' ? 'online' : 'offline';
  const slideshow = hb.slideshow_active === null || hb.slideshow_active === undefined
    ? 'unknown' : (hb.slideshow_active ? 'active' : 'inactive');
  const displayed = hb.displayed_photo && hb.displayed_photo.filename
    ? esc(hb.displayed_photo.filename) : '(none reported)';
  const occ = hb.occupancy ? esc(JSON.stringify(hb.occupancy)) : '(none)';
  return `
    <div class="hb_card" data-hb-id="${esc(hb.id)}">
      <h3>${esc(hb.id)}</h3>
      <div class="hb_state">
        bridge: <span class="${stateCls}">${esc(hb.state)}</span>
        &middot; slideshow: ${esc(slideshow)}
        &middot; occupancy: ${occ}
      </div>
      <div class="hb_displayed">displaying: ${displayed}</div>
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
      </div>
    </div>
  `;
}

function wireCard(cardEl) {
  const hbId = cardEl.getAttribute('data-hb-id');
  const getCfg = name => {
    const inp = cardEl.querySelector(`input[data-cfg="${name}"]`);
    return inp ? inp.value.trim() : '';
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
