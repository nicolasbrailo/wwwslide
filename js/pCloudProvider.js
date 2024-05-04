function getParameterByName(name, url) {
    if (!url) url = window.location.href;
    name = name.replace(/[\[\]]/g, '\\$&');
    // NB: There's a # besides ? and &, pcloud seems to use # to separate the URL args
    var regex = new RegExp('[?&#]' + name + '(=([^&#]*)|&|#|$)'),
        results = regex.exec(url);
    if (!results) return null;
    if (!results[2]) return '';
    return decodeURIComponent(results[2].replace(/\+/g, ' '));
}


const STOREKEY_AUTH_TOK = 'STOREKEY_AUTH_TOK';

function ensureAccessToken(persist, oauth_client_id, redir_uri) {
  if (getParameterByName('refresh_access_token')) {
    console.log("Force refresh access token");
    persist.remove(STOREKEY_AUTH_TOK);
  }

  if (getParameterByName('access_token')) {
    console.log("Found new AUTH details, updating local storage");
    persist.save(STOREKEY_AUTH_TOK, {
      access_token: getParameterByName('access_token'),
      userid: getParameterByName('userid'),
      locationid: getParameterByName('locationid'),
      hostname: getParameterByName('hostname'),
    });
  }

  if (!persist.get(STOREKEY_AUTH_TOK)) {
    console.log("Can't find AUTH details, redir to pCloud for auth");
    window.location.href = `https://my.pcloud.com/oauth2/authorize?client_id=${oauth_client_id}&response_type=token&redirect_uri=${redir_uri}`;
    return false;
  }

  return true;
}

function pCloudBuildUrl(tok, action, params) {
  return `https://${tok.hostname}/${action}?access_token=${tok.access_token}&${params}`;
}

function pCloudDo(tok, action, params) {
  const p = mDeferred();
  mAjax({
    url: pCloudBuildUrl(tok, action, params),
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

function ensureLoggedIn(persist, oauth_client_id, redir_uri) {
  const p = mDeferred();
  const tok = persist.get(STOREKEY_AUTH_TOK);
  if (ensureAccessToken(persist, oauth_client_id, redir_uri)) {
    pCloudDo(tok, 'userinfo').then(usr => {
      if (usr.email) {
        p.resolve(tok, usr);
      } else {
        p.reject("User not valid", usr);
      }
    });
  }
  return p;
}

function ls(tok, basepath) {
  return pCloudDo(tok, 'listfolder', `path=${basepath}`);
}

function lsDirs(tok, basepath) {
  return pCloudDo(tok, 'listfolder', `path=${basepath}&nofiles=1`);
}

class pCloudProvider {
  constructor(localdb, oauth_client_id, redir_uri, basePath) {
    this.rebuildIndex = this.rebuildIndex.bind(this);

    this.basePath = basePath;

    this.KNOWN_ALBUMS_KEY = 'PCLOUD_LS';
    this.ALBUM_PREFIX_KEY = 'PCLOUD_AL';

    this.db = localdb;
    this.tok = null;
    this.usr = null;
    this.knownAlbums = null;
    this.currentAlbum = 2;
    this.currentPicIdx = 1;

    ensureLoggedIn(this.db, oauth_client_id, redir_uri).then( (tok, usr) => {
      this.tok = tok;
      this.usr = usr;
      this.knownAlbums = this.db.get(this.KNOWN_ALBUMS_KEY);
      if (!this.knownAlbums || this.knownAlbums.length == 0) {
        this.rebuildIndex();
      }
    }).catch(console.err);
  }

  rebuildIndex() {
    console.log("Rebuilding pCloud album list");
    ls(this.tok, this.basePath).then(ls => {
      if (ls.error) {
        console.error(`Error fetching album list: ${ls.error}`);
        return;
      }
      if (!ls?.metadata?.contents) {
        console.error("No dirs");
        return;
      }
      this.knownAlbums = ls.metadata.contents.map(o => o.path);
      this.db.save(this.KNOWN_ALBUMS_KEY, this.knownAlbums);
      console.log(`Discovered ${this.knownAlbums.length} pCloud albums`);
    });
  }

  getAlbumContent(path) {
    const p = mDeferred();

    const albumKey = `${this.ALBUM_PREFIX_KEY}${path}`;
    const cachedLs = this.db.get(albumKey);
    if (cachedLs) {
      p.resolve(cachedLs);
      return p;
    }

    console.log(`Need to request contents for album ${path}`);
    ls(this.tok, path).then( ls => {
      if (ls.error) {
        console.error(`Error fetching album contents: ${ls.error}`);
        p.reject(ls.error);
        return;
      }
      if (!ls?.metadata?.contents) {
        console.error(`Album ${path} has no contents`);
        p.reject(`Album ${path} has no contents`);
        return;
      }

      const albumContent = ls.metadata.contents.map(o => o.path);
      this.db.save(albumKey, albumContent);
      p.resolve(albumContent);
    });
    return p;
  }

  getNext() {
    const notReady = mDeferred();
    notReady.resolve(null);
    if (!this.knownAlbums) {
      return notReady;
    }

    const p = mDeferred();
    const path = this.knownAlbums[this.currentAlbum];
    this.getAlbumContent(path).then((pics) => {
      const picUrl = pics[this.currentPicIdx];
      this.currentPicIdx = (this.currentPicIdx+1) % pics.length;
      console.log(picUrl);

      pCloudDo(this.tok, 'getfilelink', `path=${picUrl}`)
        .then(link => {
          p.resolve(`https://${link.hosts[0]}${link.path}`);
        })
        .catch(p.reject);
    }).catch(p.reject);

    return p;
  }
}


