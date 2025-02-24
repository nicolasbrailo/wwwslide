

/*


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

class App {
  constructor(cfgDB, imageProvider) {
    this.transitionTimeSeconds = cfgDB.get('cfg_slideshow_transition_time', 45);
    this.imageInfoShownPct = 50;
    this.imageInfoMode = getConfigImageInfoMode(cfgDB);

    this.imageProvider = imageProvider;
    this.wakeLock = new WakeupManager();

    this.app_visibility = new VisibilityCallback();
    this.pausedOnAppHidden = false;
    this.app_visibility.app_became_visible = () => {
      if (this.pausedOnAppHidden) {
        console.log("App became visible and was running; will resume")
        this.pausedOnAppHidden = false;
        this.start();
      }
    }
    this.app_visibility.app_became_hidden= () => {
      if (this.transitionJob) {
        console.log("App became hidden, will pause")
        this.pausedOnAppHidden = true;
        this.stop();
      }
    }

    this.transitionTimeMs = this.transitionTimeSeconds * 1000;
    this.transitionJob = null;
    this.metadataHideTimeMs = this.transitionTimeSeconds * 1000 * (this.imageInfoShownPct / 100);
    this.metadataHideJob = null;

    this.stop = this.stop.bind(this);
    this.start = this.start.bind(this);
    this.toggle = this.toggle.bind(this);
    this.showNext = this.showNext.bind(this);
    this.updateMeta = this.updateMeta.bind(this);
    this.hideMetadata = this.hideMetadata.bind(this);

    m$('image_holder').addEventListener('load', this.updateMeta);
  }

  stop() {
    clearTimeout(this.transitionJob);
    this.wakeLock.releaseWakelock();
    this.transitionJob = null;
  }

  start() {
    this.transitionJob = setTimeout(this.showNext, this.transitionTimeMs);
    this.wakeLock.wakelock();
    this.showNext();
  }

  toggle() {
    if (this.transitionJob) {
      this.stop();
    } else {
      this.start();
    }
  }

  showPrev() {
    console.error("showPrev not impl");
  }

  showNext() {
    this.imageProvider.getNext().then(img => {
      console.log("Image provider sends", img);

      // If transitionJob is not null, the app is in slidshow mode - schedule the next
      if (this.transitionJob) {
        // clear old timeout first, in case showNext was called directly instead of being called by a timeout
        clearTimeout(this.transitionJob);
        this.transitionJob = setTimeout(this.showNext, this.transitionTimeMs);
      }

      if (!img) {
        console.error("Image provider not ready...");
        return;
      }

      m$('image_holder').src = img;
      if (this.imageInfoMode == ImageInfoMode.NEVER) {
        this.hideMetadata();
      } else {
        this.showMetadata();
        if (this.imageInfoMode == ImageInfoMode.TIMEOUT) {
          clearTimeout(this.metadataHideJob);
          this.metadataHideJob = setTimeout(this.hideMetadata, this.metadataHideTimeMs);
        }
      }
    });
  }

  updateMeta() {
    const imgEl = m$('image_holder');
    imgEl.exifdata = null;
    EXIF.getData(imgEl, () => {
      updateTextFromExif(imgEl.exifdata, m$('image_info'));
    });
  }

  hideMetadata() {
    m$('image_info').style.display = 'none';
  }
};


const db = new LocalStorageManager();
window.app = new App(db);
window.appui = new AppUI(app);
app.showNext();
*/


class ImgProvider{
  constructor() {
  }

  getNext() {
    const p = mDeferred();
    p.resolve(`/get_next_img?t=${Date.now()}`);
    return p;
  }

  getPrev() {
    const p = mDeferred();
    p.resolve(`/get_prev_img?t=${Date.now()}`);
    return p;
  }

  resetAlbum() {
    const p = mDeferred();
    p.resolve(`/reset_album?t=${Date.now()}`);
    return p;
  }

  getCurrentImgMeta() {
    const p = mDeferred();
    mAjax({
      url: `/get_current_img_meta?t=${Date.now()}`,
      type: 'get',
      //dataType: 'json',
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
};


class App {
  constructor(imgProvider) {
    this.imgProvider = imgProvider;

    this.transitionTimeMs = 10 * 1000;
    this.slideshowEnabled = false;
    this.transitionJob = null;

    this.showNext = this.showNext.bind(this);
    this.showPrev = this.showPrev.bind(this);
    this.selectNewAlbum = this.selectNewAlbum.bind(this);
    this.toggleSlideshow = this.toggleSlideshow.bind(this);
    this._showMetadata = this._showMetadata.bind(this);
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
    } else {
      console.log("Slideshow is now on");
      this.showNext();
    }
  }

  _displayImg(requestImg) {
    requestImg().then(img => {
      if (!img) {
        console.error("Image provider not ready...");
        return;
      }

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

window.imgProvider = new ImgProvider();
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

m$('app_ctrl_cfg').addEventListener('click', toggleConfig);
m$('app_ctrl_reload').addEventListener('click', app.selectNewAlbum);
m$('app_ctrl_prev').addEventListener('click', app.showPrev);
m$('app_ctrl_next').addEventListener('click', app.showNext);
m$('app_ctrl_toggle').addEventListener('click', toggleSlideshow);

toggleSlideshow();

