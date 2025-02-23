from pymethodecache.cache import cache_func
import exifread
import json
import os
import requests

def convert_to_degrees(value):
    """Helper function to convert the GPS coordinates stored in EXIF format to degrees."""
    d = float(value.values[0].num) / float(value.values[0].den)
    m = float(value.values[1].num) / float(value.values[1].den)
    s = float(value.values[2].num) / float(value.values[2].den)
    return d + (m / 60.0) + (s / 3600.0)

def extract_gps(tags):
    if not tags or \
       not tags.get('GPS GPSLatitude') or \
       not tags.get('GPS GPSLatitudeRef') or \
       not tags.get('GPS GPSLongitude') or \
       not tags.get('GPS GPSLongitudeRef'):
        return None
    lat = convert_to_degrees(tags.get('GPS GPSLatitude'))
    lon = convert_to_degrees(tags.get('GPS GPSLongitude'))
    if tags.get('GPS GPSLatitudeRef').values[0] != 'N':
        lat = -lat
    if tags.get('GPS GPSLongitudeRef').values[0] != 'E':
        lon = -lon
    return {"lat": lat, "lon": lon}

def extract_keys(dic, interesting_keys):
    return {k: dic[k] for k in interesting_keys if k in dic}

def extract_all_exif(img_fullpath):
    exif = {}
    with open(img_fullpath, 'rb') as fp:
        tags = exifread.process_file(fp, details=False)
        for k,v in tags.items():
            exif[k] = str(v)
        exif["gps"] = extract_gps(tags)
    return exif

@cache_func('cache/wget.pkl')
def wget(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:128.0) Gecko/20100101 Firefox/128.0',
    }
    response = requests.get(url, headers=headers)
    content = response.content.decode('utf-8')
    return content

def add_rev_geo(exif, rev_geo_apikey):
    if rev_geo_apikey is None or len(rev_geo_apikey) == 0 or "gps" not in exif:
        return
    lat = exif["gps"]["lat"]
    lon = exif["gps"]["lon"]
    url = f"https://api.geoapify.com/v1/geocode/reverse?lat={round(lat, 3)}&lon={round(lon, 3)}&format=json&apiKey={rev_geo_apikey}"
    try:
        loc_req = wget(url)
        loc = json.loads(loc_req)["results"][0]
        if "formatted" in loc:
            loc["revgeo"] = loc["formatted"]
        filt_loc = extract_keys(loc, ["country", "state", "city", "postcode", "revgeo", "address_line1", "address_line2"])
        exif["reverse_geo"] = filt_loc
    except KeyError:
        exif["reverse_geo"] = None


def get_img_meta(img_directory, img_fullpath, rev_geo_apikey):
    if not img_fullpath.startswith(img_directory):
        raise ValueError(f"Invalid image path {path}")
    exif = extract_all_exif(img_fullpath)
    add_rev_geo(exif, rev_geo_apikey)
    interesting_meta = ["gps", "reverse_geo", "EXIF ExifImageWidth", "EXIF ExifImageLength", "EXIF DateTimeOriginal", "Image Make", "Image Model"]
    meta = extract_keys(exif, interesting_meta)
    meta['local_path'] = img_fullpath
    meta['filename'] = os.path.basename(img_fullpath)
    meta['albumpath'] = os.path.dirname(img_fullpath)
    meta['albumname'] = os.path.dirname(img_fullpath)[len(img_directory):]
    return meta

