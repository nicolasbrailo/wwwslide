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

function buildTextFromExif(meta) {
  function gpsText(meta) {
    // TODO https://www.mapbox.com/pricing geocode
    if (!meta.GPSLatitude || !meta.GPSLatitudeRef) return null;
    if (!meta.GPSLongitude || !meta.GPSLongitudeRef) return null;
    if (meta.GPSLatitude.length != 3) return null;
    if (meta.GPSLongitude.length != 3) return null;
    const mkPart = p => `${p[0]}° ${p[1]}' ${Math.floor(p[2])}''`;
    const lat = `${mkPart(meta.GPSLatitude)} ${meta.GPSLatitudeRef}`;
    const lon = `${mkPart(meta.GPSLongitude)} ${meta.GPSLongitudeRef}`;
    return `${lat}, ${lon}`;
  }

  const metaT = [];
  metaT.push(`Photo taken ${meta.DateTime}`);
  const gps = gpsText(meta);
  if (gps) {
    metaT.push(`Location: ${gps}`);
  }
  return metaT.join('\n');
}

const ImageInfoMode = Object.freeze({
    ALWAYS: 0,
    NEVER: 1,
    TIMEOUT: 2,
});

class App {
  constructor(imageProvider) {
    this.transitionTimeSeconds = 5;
    this.imageInfoShownPct = 50;
    this.imageInfoMode = ImageInfoMode.TIMEOUT;

    this.imageProvider = imageProvider;
    this.wakeLock = new WakeupManager();

    this.transitionTimeMs = this.transitionTimeSeconds * 1000;
    this.transitionJob = null;
    this.metadataHideTimeMs = this.transitionTimeSeconds * 1000 * (this.imageInfoShownPct / 100);
    this.metadataHideJob = null;

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
    this.transitionJob = setInterval(this.showNext, this.transitionTimeMs);
    this.wakeLock.wakelock();
    this.showNext();
  }

  showNext() {
    this.imageProvider.getNext().then(img => {
      // TODO use timeout instead of interval, so that time of display isn't dependant on loading time
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
          this.metadataHideJob = setInterval(this.hideMetadata, this.metadataHideTimeMs);
        }
      }
    });
  }

  updateMeta() {
    const imgEl = m$('image_holder');
    imgEl.exifdata = null;
    EXIF.getData(imgEl, () => {
      m$('image_info').innerText = buildTextFromExif(imgEl.exifdata)
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
app.showNext();
