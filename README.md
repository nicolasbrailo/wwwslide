# wwwslide

wwwslide is a client/server for LAN slideshows. If you have a large picture collection and want a way to display them in multiple places, wwwslide server will create a web interface to retrieve random pictures from a single url. The web client can display these pictures, but there is no reason to use the included client: you could curl wwwslide and pipe it to an image viewer.

[![](/blog_img/1009_wwwslide.jpg)](/blog_img/1009_wwwslide.jpg)

^ looks like this, sans cool picture

## How it works

wwwslide has a server that can be pointed to a local pictures directory. It expects that pictures will be grouped in albums, sorted by `/$year/$arbitrary_name/*.jpg` (eg `2019/foo/bar/album/*.jpg`). On startup, it will pick up one album, randomly, and serve a few pictures from this album to anyone calling its `/get_image` web endpoint. Once it runs out of pictures for this album, it will select a new random album (with a new random subset of pictures).

The included client (which can be accessed on the root of the server) can be used to browser this picture (just point your browser to your wwwslide LAN address). It's not very smart, but it should work!


## Cool features

* Remote control: each picture includes a QR code. Scanning the QR will take you to a local page with metadata of the shown image. This page can also be used to control wwwslide (eg to request that this album is displayed from the start, or to select a new album)
* Reverse geolocation: the metadata of each picture includes a reverse-geolocation. No need to guess where you took a picture, wwwslide will guess for you (as long as your pictures have geotags in their exif data)
* Multiple clients can display different pictures from the same album: you can keep multiple kiosk-mode displays all pointed to wwwslide. They will all show the same album, but different pictures from it. This makes for a very interesting effect in a single room.


## Security

The server is meant to be used in a LAN only; it uses a development web server and has little security, so consider any wwwslide instance exposed to the outside world as automatically pwnd.

# TODO
* Make the client work in Chromecast
* Add controller support to select album, or year
* Add metadata scanning to create slideshows per category (eg by geolocation)
* Add face scanning to create slideshow per person

