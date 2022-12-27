# pixiv-bookmarks-explorer
A tool to back up and explore your favorite pixiv artworks in case they get deleted.

# Disclaimer
This application is NOT production-ready and shouldn't be treated as such.  
It is not uWSGI-ready, meaning it will only run as a single worker application.
Either configure uWSGI (or your WSGI server) properly to only spawn a single worker, or use the embedded werkzeug development server.  
Failing to configure your WSGI server properly may cause a de-synchronization with artworks, resulting in potential data loss or corruption if refresh or delete is used, as artworks are only loaded on application start.

The provided app_key can be modified, and only allows Flask's flash() method to work properly.

# Setup and run
*The following setup guide assumes that you have a valid Python (and pip) as well as git installed on your machine.*
1. Grab your pixiv refresh token. You can use [this gist](https://gist.github.com/ZipFile/c9ebedb224406f4f11845ab700124362) to retrieve your own refresh token. Save it for later.
2. Clone the repository with `git clone github.com/Proxymiity/pixiv-bookmarks-explorer`
3. Run `pip install -r requirements.txt` (you may need to use `pip3`, `python -m pip` or `python -m pip3` depending on your OS.)
4. Edit `config.json` (see the config sample below for more info)
5. Run `python app.py` and visit the address printed to the console.

# Configuration sample
```python
{
    "pixiv": {
        "access": "",
        "refresh": ""
    },
    "display": {
        "home": {
            "image": "original",
            "ipp": "50",
            "order": "default"
        },
        "artwork": {
            "image": "original"
        },
        "nsfw": "hidden"
    },
    "app_key": "3A#RSiFq5zO4qMqO22gnF65B&9ayUSD^6Bwh3we@JIlCF$wkf#gi$Y%A%xKW3iZTIo",
    "read_only": false,
    "read_only_token": "O5yvij95F2C3AibqmYvRZhu0",
    "temp_path": "./tmp",
    "filesystem": "local",
    "filesystem_options": {
        "path": "./data",
        "server": "",
        "token": "",
        "proxy": false
    }
}
```
- `pixiv.access` refers to your pixiv access token, which will be updated accordingly. It is not mandatory.
- `pixiv.refresh` refers to your pixiv refresh token. It is mandatory and must be valid.
- `display.*` refers to display settings, which can be changed using the GUI:
    - `display.home.image` sets the image format to use on the home page.
    - `display.home.ipp` sets the number of images per home page.
    - `display.home.order` defines the display order for artworks on the home page.
    - `display.artwork.image` sets the image format to use when viewing artworks.
    - `display.nsfw` sets the 'Not Safe For Work' artwork policy. (see below)
- `app_key` is mandatory in order to display warnings/errors, using sessions.
- `read_only` makes the application read-only, preventing clients from refreshing or deleting artworks. (see below)
- `read_only_token` specifies the token used to refresh or delete artworks while the app is read-only.
- `temp_path` sets the temporary path where artworks are downloaded before they are copied/uploaded.
- `filesystem` sets whether to use local or remote storage:
    - `filesystem_options.path` sets the location where artworks are stored if using `filesystem = local`
    - `filesystem_options.server` sets the URL of the storage server if using `filesystem = remote` (see below)
    - `filesystem_options.token` sets the token of the remote storage server if using `filesystem = remote`
    - `filesystem_options.proxy` sets whether to proxy images from the storage server or redirect the client to the server if using `filesystem = remote`

# Deployment and read-only state
As mentioned earlier, this app shouldn't be deployed to public. But, if you want to expose this app to the web, you should be aware that anyone can trigger a refresh or delete artworks.  
This could result in issues:
- Users deleting artworks you downloaded (which isn't a big deal if they're still available)
- Users spamming the refresh endpoint (which could probably result in an account termination for scripting/scraping)

When deploying, set the `read_only` property to `true` in the config, and set a token in `read_only_token`, which will allow you to refresh or delete artworks via the `/admin` endpoint.

Keep in mind that, as mentioned earlier too, you shouldn't deploy this application, especially if you plan to use a WSGI server instead of werkzeug's internal server.

# Artwork storage
There are two ways to store artworks.
- Locally
    - Uses your local filesystem to store all image data
    - No hassles, supported out of the box
    - Supports mounts to other disks
    - Fastest
- Remotely
    - Uses a tiny PHP backend to store/delete artworks
    - [Requires installation](https://github.com/Proxymiity/php-fs)
    - Theoretically supports endless storage when using on AWS
    - "Fast". It may be the fastest option depending on how fast your FS is and a bunch of other factors related to python and flask
    - Redirects the client to the image, but can be configured to proxy images to act as local storage to the client

FYI, storing 1508 artworks represents 6.3 GB of image data and 4.9 MB of metadata. This includes all metadata from pixiv as well as reduced versions (large/medium/square).

# NSFW policies
There are 4 policies for NSFW.  
Those options are only effective for the frontend. User or instance settings won't be verified on `/i/<ID>` (direct image links) or `</a/ID/{zip,pdf}>`.
- `enabled`  
  Display all NSFW artworks.  
  Users cannot override this setting.
- `hidden`  
  Hide all NSFW artworks from the homepage. Those artworks can still be accessed via their `/a/<ID>` page.  
  Users can override this setting, allowing NSFW on the homepage.
- `required`  
  Hide all NSFW artworks from all pages.  
  Users can override this setting, allowing NSFW on all pages.
- `disabled`  
  Completely disable NSFW on the instance. Those artworks will still be downloaded, but won't be shown in the homepage or artwork page.
  Users cannot override this setting.

# Routes
- `/` Artwork list
  - `/p/<page>` Specified page of artwork list
  - `/p/<page>/<image quality>/<images per page>/<order>` Specified page of artwork list with preview parameters (iq: original, large, medium, square_medium) (order: default (by ingress date), artwork (by creation date))
- `/a/<id>` Artwork details
  - `/a/<id>/<image quality>` Artwork details with specified image quality
  - `/a/<id>/pdf` Download artwork as PDF
    - `/a/<id>/pdf/<image quality>` Download artwork as PDF with specified image quality
  - `/a/<id>/zip` Download artwork as ZIP
    - `/a/<id>/zip/<image quality>` Download artwork as ZIP with specified image quality
  - `/a/<id>/meta` Artwork JSON metadata
  - `/a/<id>/delete` Delete specified artwork
  - `/a/<id>/pixiv` View artwork page on pixiv
  - `/a/<id>/user-pixiv` View artist profile on pixiv
- `/i/<id>/<image>` Download specific image of artwork
  - `/i/<id>/<image>/<image quality>` Download specific image of artwork with specific quality
- `/display/home` POST for artwork display settings (image quality, images per page, artwork order)
- `/display/artwork` POST for artwork display settings (image quality)
  - `/display/artwork/<r>` POST for artwork display settings (image quality) (r: redirect to artwork)
- `/display/nsfw/<setting>?r=<r>` Set the NSFW cookie (enable, disable) (r: redirect to path after cookie definition)
- `/refresh` Trigger artwork list refresh
- `/admin` GET/POST for admin page for read-only instances