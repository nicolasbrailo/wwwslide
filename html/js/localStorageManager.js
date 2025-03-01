const MAX_CACHE_AGE_SECS = 60 * 60 * 24 * 3;

class LocalStorageManager {
  constructor() {
    this.max_cache_age_secs = MAX_CACHE_AGE_SECS;
    this.cache_idx = this.get('cache_idx', {});
    if (typeof(this.cache_idx) != typeof({})) {
      console.error("Can't read local storage, will clear cache");
      this.cache_idx = {};
      this.save('cache_idx', this.cache_idx);
      localStorage.clear();
    }
  }

  get(key, default_val) {
    const item = localStorage.getItem(key);
    if (item === null) {
      return default_val;
    }

    try {
      return JSON.parse(item);
    } catch (e) {
      return default_val;
    }
  }

  save(key, val) {
    localStorage.setItem(key, JSON.stringify(val));
  }

  remove(key) {
    localStorage.removeItem(key);
  }

  _cacheGet(key, ignoreExpireDate=false) {
    const last_update = this.cache_idx[key] || 0;
    const age = Date.now() - last_update;
    const cache_is_old = (age > 1000 * this.max_cache_age_secs);
    if (cache_is_old && !ignoreExpireDate) {
      localStorage.removeItem(key);
      return null;
    }
    return this.get(key, null);
  }

  cacheGet(key) {
    return this._cacheGet(key);
  }

  cacheGet_ignoreExpire(key) {
    return this._cacheGet(key, true);
  }

  cacheSave(key, val) {
    this.cache_idx[key] = Date.now();
    this.save('cache_idx', this.cache_idx);
    this.save(key, val);
  }
};
