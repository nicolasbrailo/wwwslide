class RelFsProvider {
  constructor() {
    this.idx = 0;
    this.imgs = [
      "Durmiendo/20230813_141634.jpg",
      "Durmiendo/20240321_164328.jpg",
      "Durmiendo/20231211_202420.jpg",
      "Durmiendo/20240316_220516.jpg",
      "Durmiendo/20240225_081020.jpg",
      "Durmiendo/DSC_0123.JPG",
      "Durmiendo/DSC_0135.JPG",
      "Durmiendo/20220604_190333.jpg",
      "Durmiendo/DSC_0156.JPG",
      "Durmiendo/DSC_0172.JPG",
      "Durmiendo/DSC_3144.JPG",
      "Durmiendo/DSC_3563.JPG",
      "Durmiendo/DSC_3763.JPG",
    ];
  }

  getNext() {
    const p = mDeferred();
    this.idx = (this.idx + 1) % this.imgs.length;
    p.resolve(this.imgs[this.idx]);
    return p;
  }
};

class LocalPyProvider {
  constructor() {
  }

  getNext() {
    const p = mDeferred();
    p.resolve(`/get_image?t=${Date.now()}`);
    return p;
  }
};


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

// TODO serialize to local storage
GPS_REVGEO_CACHE = {};
function updateTextFromExif(meta, textEl, betterGps=null) {
  function metaHasGps(meta) {
    if (!meta.GPSLatitude || meta.GPSLatitude.length != 3) return false;
    if (!meta.GPSLongitude || meta.GPSLongitude.length != 3) return false;
    if (!meta.GPSLatitudeRef || ("NS".indexOf(meta.GPSLatitudeRef.toUpperCase()) == -1)) return false;
    if (!meta.GPSLongitudeRef || ("WE".indexOf(meta.GPSLongitudeRef.toUpperCase()) == -1)) return false;
    return true;
  }

  function reverseGeocode(meta) {
    if (!metaHasGps(meta)) return null;
    const geoApiKey = db.get('cfg_geoapify_api_key');
    if (!geoApiKey) return null;

    function dg(d,m,s,r) {
      const R = ("WS".indexOf(r.toUpperCase()) != -1)? -1 : 1;
      return R * (d + m/60 + s/3600);
    };
    const lat = dg(meta.GPSLatitude[0], meta.GPSLatitude[1], meta.GPSLatitude[2], meta.GPSLatitudeRef);
    const lon = dg(meta.GPSLongitude[0], meta.GPSLongitude[1], meta.GPSLongitude[2], meta.GPSLongitudeRef);

    const geo_key = `${Math.floor(lat / 0.01)}|${Math.floor(lon / 0.01)}`;
    if (geo_key in GPS_REVGEO_CACHE) {
      const cached = GPS_REVGEO_CACHE[geo_key];
      console.log(`Using ${lat}:${lon} from cached ${geo_key} = ${cached}`);
      return cached;
    }

    console.log(`Request location for ${lat}:${lon}`);
    mAjax({
      url: `https://api.geoapify.com/v1/geocode/reverse?lat=${lat}&lon=${lon}&format=json&apiKey=${geoApiKey}`,
      type: 'get',
      dataType: 'json',
      error: console.error,
      success: revgeo => {
        window.revgeo = revgeo
        revgeo.results[0]
        if (!revgeo?.results?.length) {
          console.error(`Can't reverse geocode ${lat};${lon}: ${revgeo}`);
          return;
        }
        const res = revgeo.results[0];
        //const revgeoT = res.formatted
        const revgeoT = `${res.street}, ${res.city}, ${res.country}`;
        // Recurse with a better gps description
        updateTextFromExif(meta, textEl, betterGps=revgeoT);

        // Cache
        GPS_REVGEO_CACHE[geo_key] = revgeoT;
      },
    });
  }

  function gpsText(meta) {
    if (!metaHasGps(meta)) return null;
    const mkPart = p => `${p[0]}° ${p[1]}' ${Math.floor(p[2])}''`;
    const lat = `${mkPart(meta.GPSLatitude)} ${meta.GPSLatitudeRef}`;
    const lon = `${mkPart(meta.GPSLongitude)} ${meta.GPSLongitudeRef}`;
    return `${lat}, ${lon}`;
  }

  function takenTime(meta) {
    if (meta.DateTimeOriginal) return meta.DateTimeOriginal;
    if (meta.DateTime) return meta.DateTime;
    return null;
  }

  const metaT = [];
  const takenTimeT = takenTime(meta);
  if (takenTimeT) {
    metaT.push(`Photo taken ${takenTimeT}`);
  }

  if (betterGps) {
    metaT.push(betterGps);
  } else {
    // Schedule a reverseGeocode update
    // TODO: This has a race condition, if the revgeo response takes too much time it could update another image
    const maybeCached = reverseGeocode(meta);
    if (maybeCached) {
        metaT.push(maybeCached);
    } else {
      const gps = gpsText(meta);
      if (gps) {
        metaT.push(`Location: ${gps}`);
      }
    }
  }

  textEl.innerText = metaT.join('\n');
}

const ImageInfoMode = Object.freeze({
    ALWAYS: 0,
    NEVER: 1,
    TIMEOUT: 2,
});

class App {
  constructor(imageProvider) {
    this.transitionTimeSeconds = 30;
    this.imageInfoShownPct = 50;
    this.imageInfoMode = ImageInfoMode.ALWAYS;

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
    this.showMetadata = this.showMetadata.bind(this);
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

  showMetadata() {
    m$('image_info').style.display = '';
  }

  hideMetadata() {
    m$('image_info').style.display = 'none';
  }
};

const db = new LocalStorageManager();
window.fsprovider = new RelFsProvider();
window.pyprovider = new LocalPyProvider();

const OAUTH_CLIENT_ID = "TODO";
const REDIR_URI = "TODO";
//window.pcProvider = new pCloudProvider(db, OAUTH_CLIENT_ID, REDIR_URI, '/Fotos/2017/Holanda');

window.app = new App(pyprovider);

//m$('app_ctrl_cfg').addEventListener('click', () => { window.location.href = '/config.html'});
m$('app_ctrl_cfg').addEventListener('click', () => { window.location.href = '/'});
m$('app_ctrl_prev').addEventListener('click', app.showPrev);
m$('app_ctrl_next').addEventListener('click', app.showNext);
m$('app_ctrl_toggle').addEventListener('click', app.toggle);

app.showNext();

document.addEventListener('keydown', event => {
  if (event.keyCode === 37) {
    app.showPrev();
  } else if (event.keyCode === 39) {
    app.showNext();
  }
});



var showCtrlsTimeout = null;
function showCtrls() {
  m$('app_ctrl').style.display = '';
  clearTimeout(showCtrlsTimeout);
  function hideCtrls() {
    m$('app_ctrl').style.display = 'none';
  }
  showCtrlsTimeout = setTimeout(hideCtrls, 5000);
}
showCtrls();


var touchstartX = 0;
var touchstartY = 0;
document.addEventListener('touchstart', event => {
  touchstartX = event.changedTouches[0].screenX;
  touchstartY = event.changedTouches[0].screenY;
  showCtrls();
}, false);


document.addEventListener('touchend', event => {
  const dx = touchstartX - event.changedTouches[0].screenX;
  const dy = touchstartY - event.changedTouches[0].screenY;

  if (dx < -50) {
    app.showPrev();
  } else if (dx > 50) {
    app.showNext();
  }

  event.stopPropagation();
}, false);
