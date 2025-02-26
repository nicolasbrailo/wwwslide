// Stop device from sleeping (eg for slideshows on mobile devices)
class WakeupManager {
  constructor() {
    this.wakeLock = null;
  }

  async wakelock() {
    if (!navigator.wakeLock) {
      console.log("Wakelock not supported by browser");
    } else {
      this.wakeLock = await navigator.wakeLock.request("screen");
      console.log("Acquired wakelock");
    }
  }

  releaseWakelock() {
    this.wakeLock = null;
    console.log("Stopping: Released wakelock");
  }
};

class ImgProvider{
  constructor(app_cfg) {
    this.getNext = this.getNext.bind(this);
    this.getPrev = this.getPrev.bind(this);
    this.resetAlbum = this.resetAlbum.bind(this);
    this.getCurrentImgMeta = this.getCurrentImgMeta.bind(this);
    this.setEmbedQr = this.setEmbedQr.bind(this);
    this.setTargetSize = this.setTargetSize.bind(this);
    this.loadFullAlbum = this.loadFullAlbum.bind(this);

    this.app_cfg = app_cfg;
    this.client_id = null;
    this.when_ready_cb = null;

    mAjax({
      url: `/client_register`,
      success: id => {
          this.client_id = id;
          // This is racy, but for LAN should be fine
          this.setEmbedQr(this.app_cfg.get('shouldEmbedQr', true));
          this.setTargetSize(this.app_cfg.get('target_size_w', 1024),
                             this.app_cfg.get('target_size_h', 768));
          if (this.when_ready_cb) this.when_ready_cb();
        },
    });
  }

  whenReady(cb) {
    this.when_ready_cb = cb;
    if (this.client_id) {
      // Already init'd
      cb();
    }
  }

  getNext() {
    if (!this.client_id) return null;
    const p = mDeferred();
    // This doesn't make a request, it directly returns a url for the image src.
    // The browser will make a request whenever it wants to.
    p.resolve(`/get_next_img/${this.client_id}?t=${Date.now()}`);
    return p;
  }

  getPrev() {
    if (!this.client_id) return null;
    const p = mDeferred();
    p.resolve(`/get_prev_img/${this.client_id}?t=${Date.now()}`);
    return p;
  }

  resetAlbum() {
    if (!this.client_id) return null;
    const p = mDeferred();
    p.resolve(`/reset_album/${this.client_id}?t=${Date.now()}`);
    return p;
  }

  getCurrentImgMeta() {
    if (!this.client_id) return null;
    const p = mDeferred();
    mAjax({
      url: `/get_current_img_meta/${this.client_id}`,
      error: p.reject,
      success: obj => {
        try {
          p.resolve(JSON.parse(obj));
        } catch (x) {
          p.reject(x);
        }
      },
    });
    return p;
  }

  setEmbedQr(should_embed) {
    if (!this.client_id) return null;
    this.app_cfg.save('shouldEmbedQr', should_embed);
    mAjax({url: `/client_cfg/${this.client_id}/embed_info_qr_code/${should_embed}`});
  }

  setTargetSize(width, height) {
    if (!this.client_id) return null;
    this.app_cfg.save('target_size_w', width);
    this.app_cfg.save('target_size_h', height);
    mAjax({url: `/client_cfg/${this.client_id}/target_size/${width}x${height}`});
  }

  loadFullAlbum() {
    if (!this.client_id) return null;
    mAjax({
      url: `/show_full_album/${this.client_id}`,
      error: console.log,
      success: console.log,
    });
  }
};


class App {
  constructor(imgProvider) {
    // Where to get images
    this.imgProvider = imgProvider;

    // Slideshow config
    this.transitionTimeMs = 10 * 1000;
    this.slideshowEnabled = false;
    this.transitionJob = null;

    // Lock the device (don't sleep) while slideshow is active
    this.wakeLock = new WakeupManager();

    // Pause slideshow if window isn't visible
    this.app_visibility = new VisibilityCallback();
    this.pausedOnAppHidden = false;
    this.app_visibility.app_became_visible = () => {
      if (this.pausedOnAppHidden) {
        console.log("App became visible and was running; will resume")
        this.pausedOnAppHidden = false;
        this.toggleSlideshow();
      }
    }
    this.app_visibility.app_became_hidden= () => {
      if (this.slideshowEnabled) {
        console.log("App became hidden, will pause")
        this.pausedOnAppHidden = true;
        this.toggleSlideshow();
      }
    }

    this.showNext = this.showNext.bind(this);
    this.showPrev = this.showPrev.bind(this);
    this.selectNewAlbum = this.selectNewAlbum.bind(this);
    this.toggleSlideshow = this.toggleSlideshow.bind(this);
    this._showMetadata = this._showMetadata.bind(this);

    this.imgProvider.whenReady(this.toggleSlideshow);
  }

  showNext() {
    return this._displayImg(this.imgProvider.getNext);
  }

  showPrev() {
    return this._displayImg(this.imgProvider.getPrev);
  }

  selectNewAlbum() {
    return this._displayImg(this.imgProvider.resetAlbum);
  }

  getSlideshowActive() { return this.slideshowEnabled; }

  toggleSlideshow() {
    this.slideshowEnabled = !this.slideshowEnabled;
    this._scheduleSlideChange();
    if (!this.slideshowEnabled) {
      console.log("Slideshow is now off");
      this.wakeLock.releaseWakelock();
    } else {
      console.log("Slideshow is now on");
      this.showNext();
      this.wakeLock.wakelock();
    }
  }

  _displayImg(requestImg) {
    const img_promise = requestImg();
    if (!img_promise) {
      console.error("Image provider not ready...");
      return;
    }

    img_promise.then(img => {
      // Schedule call to showMetadata after image finished loading, to avoid race condition in loading up this or the previous' image metadata
      m$('image_info').style.display = 'none';
      m$('image_holder').onload = this._showMetadata;
      m$('image_holder').src = img;
      this._scheduleSlideChange();
    });
  }

  _scheduleSlideChange() {
    // If transitionJob is not null, the app is in slidshow mode - schedule the next
    if (this.transitionJob) {
      // clear old timeout first, in case showNext was called directly instead of being called by a timeout
      clearTimeout(this.transitionJob);
    }

    if (this.slideshowEnabled) {
      this.transitionJob = setTimeout(this.showNext, this.transitionTimeMs);
    }
  }

  _showMetadata() {
    m$('image_info').style.display = 'none';
    if (!m$('app_config_show_meta').checked) return;

    this.imgProvider.getCurrentImgMeta().then(meta => {
      const loc = meta["reverse_geo"]? '<br/>' + meta["reverse_geo"]["revgeo"] : ''
      const render = `${meta["albumname"]} @ ${meta["EXIF DateTimeOriginal"]}<br/>
                      ${meta["Image Model"]}
                      ${loc}`;
      m$('image_info').innerHTML = render;
      m$('image_info').style.display = '';
    });
  }

}

class AppUI {
  constructor(slideshow) {
    this.ss = slideshow;
    this.TOUCH_SWIPE_MIN_DISTANCE = 50;

    // Capture left/right arrows
    document.addEventListener('keydown', event => {
      if (event.keyCode === 37) {
        this.ss.showPrev();
      } else if (event.keyCode === 39) {
        this.ss.showNext();
      }
    });

    // Capture swipes
    this.touchstartX = null;
    this.touchstartY = null;
    document.addEventListener('touchstart', event => {
      this.touchstartX = event.changedTouches[0].screenX;
      this.touchstartY = event.changedTouches[0].screenY;
    }, false);

    document.addEventListener('touchend', event => {
      const dx = this.touchstartX - event.changedTouches[0].screenX;
      const dy = this.touchstartY - event.changedTouches[0].screenY;

      if (dx < -this.TOUCH_SWIPE_MIN_DISTANCE) {
        this.ss.showPrev();
      } else if (dx > this.TOUCH_SWIPE_MIN_DISTANCE) {
        this.ss.showNext();
      }

      event.stopPropagation();
    }, false);
  }

  styleSlideshowBtn(slideshowEnabled) {
    if (slideshowEnabled) {
      m$('app_ctrl_toggle').classList.add('enabled');
    } else {
      m$('app_ctrl_toggle').classList.remove('enabled');
    }
  }
};

window.app_cfg = new LocalStorageManager();
window.imgProvider = new ImgProvider(app_cfg);
window.app = new App(imgProvider);
window.app_ui = new AppUI(app);

function toggleSlideshow() {
  app.toggleSlideshow();
  app_ui.styleSlideshowBtn(app.getSlideshowActive());
}

let cfgVis = false;
function toggleConfig() {
  cfgVis = !cfgVis;
  if (cfgVis) {
    m$('app_config').style.display = 'block';
  } else {
    m$('app_config').style.display = 'none';
  }
}

function saveConfig() {
  app_cfg.save('showImgMeta', m$('app_config_show_meta').checked);
  m$('image_info').style.display = m$('app_config_show_meta').checked? "block" : "none";
  imgProvider.setEmbedQr((m$('app_config_qr').checked));
  imgProvider.setTargetSize(
              parseInt(m$('app_config_target_width').value),
              parseInt(m$('app_config_target_height').value));
  m$('app_config').style.display = "none";
}

m$('app_ctrl_next').addEventListener('click', app.showNext);
m$('app_ctrl_prev').addEventListener('click', app.showPrev);
m$('app_ctrl_toggle').addEventListener('click', toggleSlideshow);
m$('app_ctrl_cfg').addEventListener('click', toggleConfig);
m$('app_ctrl_reload').addEventListener('click', app.selectNewAlbum);
m$('app_config_save').addEventListener('click', saveConfig);
m$('app_config_load_this_album').addEventListener('click', imgProvider.loadFullAlbum);
m$('app_config_debug_clients').addEventListener('click', () => { window.open("/client_ls_txt", "_blank") });

console.log(app_cfg.get('showImgMeta', true));
console.log(app_cfg.get('shouldEmbedQr', true));
m$('app_config_show_meta').checked = app_cfg.get('showImgMeta', true);
m$('app_config_qr').checked = app_cfg.get('shouldEmbedQr', true);
m$('app_config_target_width').value = app_cfg.get('target_size_w', 1024);
m$('app_config_target_height').value = app_cfg.get('target_size_h', 768);

