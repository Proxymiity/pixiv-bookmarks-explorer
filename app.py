# DISCLAIMER: This application is NOT production-ready and shouldn't be treated as such.

# It is not uWSGI-ready, meaning it will only run as a single worker application.
# Either configure uWSGI properly to only spawn a single worker, or use the embedded werkzeug development server

# Failing to configure your WSGI server properly may cause a de-synchronization with artworks, resulting in
# potential data loss or corruption if refresh or delete is used, as artworks are only loaded on application start.

# The provided app_key can be modified, and only allows Flask's flash() method to work properly.

from flask import Flask, redirect, url_for, request, render_template, send_file, Response, make_response
import threading
from random import choice
from math import ceil
from json import dumps

import utils
from utils import conf, artworks, temp, flash

from files import make_zip, make_pdf

from objects import Artwork
import pixiv

app = Flask(__name__)
app.secret_key = conf["app_key"]


@app.route("/")
@app.route("/p/<page>")
@app.route("/p/<page>/<image>/<ipp>/<order>")
def home(page=None, image=None, ipp=None, order=None):
    _full_route = True if order else False
    _show_nsfw = utils.get_nsfw("home")
    _nsfw_pref, _nsfw_user = utils.get_nsfw_state("home")

    # Get page and display settings from config/path
    try:
        page = int(page or 1)
    except ValueError:
        flash("<b>Invalid page.</b> Falling back to page <u>1</u>.", "warning")
        page = 1
    image = image or conf["display"]["home"]["image"]
    try:
        ipp = int(ipp or conf["display"]["home"]["ipp"])
    except ValueError:
        ipp = -1
    order = order or conf["display"]["home"]["order"]

    # Check that display settings are supported, reset them in case they're not
    if image not in ("original", "large", "medium", "square_medium", "none"):
        flash("<b>Invalid display settings.</b> The image setting was set to <u>original</u>.", "warning")
        image = "original"
    if ipp < 0:
        flash("<b>Invalid display settings.</b> The images-per-page setting was set to <u>50</u>.", "warning")
        ipp = 50
    if order not in ("default", "artwork"):
        flash("<b>Invalid display settings.</b> The order setting was set to <u>default</u>.", "warning")
        order = "default"

    # Get artworks, filter them and do some pagination
    aws = Artwork.all(limit=ipp, offset=ipp * (page - 1))
    aws = [a for a in aws if (a.nsfw and _show_nsfw) or not a.nsfw]  # Probably not the most time-efficient thing to do
    computed_artworks = {a: artworks[a] for a in artworks
                         if ((artworks[a]["x_restrict"] > 0) and _show_nsfw) or artworks[a]["x_restrict"] == 0}
    if ipp > 0:
        pages = ceil(len(computed_artworks) / ipp)
        pagination = utils.gen_paginate_data(page, pages, f"/p/{{}}/{image}/{ipp}/{order}" if _full_route else "/p/{}",
                                             margin=5)
    else:  # Remove pagination in case ipp = max, leaving pagination would raise a DivisionByZeroError
        pagination = []
    if order == "artwork":
        aws.sort(key=lambda x: x.post_date, reverse=True)
    return render_template("home.html", artworks=aws,
                           display_config=conf["display"]["home"], image=image,
                           pagination=pagination,
                           ro=conf["read_only"], nsfw_master=_nsfw_pref, nsfw=_nsfw_user)


@app.route("/random")
def random():
    r = choice(list(artworks.keys()))
    return redirect(url_for("artwork_show", artwork=r))


@app.route("/refresh")
def refresh():
    # Check for blocking states
    if conf["read_only"]:
        flash("<b>Application is read-only.</b> Cannot refresh artworks.", "danger")
        return redirect(url_for("home"))
    if temp.get("refresh_lock", False):
        flash("<b>Error.</b> Already refreshing. Please wait or check the console for progress info.", "danger")
        return redirect(url_for("home"))

    # Start the background refresh thread
    t = threading.Thread(target=_background_refresh)
    t.start()
    flash("<b>Refreshing metadata and new artworks.</b> This operation can take some time.", "success")
    return redirect(url_for("home"))


def _background_refresh():
    # Get bookmarks, update their metadata locally and download the new ones
    print("Now refreshing metadata from pixiv, this can take a while...")
    temp["refresh_lock"] = True
    bookmarks = pixiv.get_bookmarks()
    utils.update_metadata(bookmarks)
    new = utils.filter_artworks(bookmarks)
    new.reverse()

    # Download bookmarks to the temporary directory
    print(f"There are {len(new)} new bookmarks to download.")
    for b in new:
        pixiv.download_bookmarks(b)

    # Copy bookmarks to the storage backend (local/remote)
    print("Bookmarks downloaded. Now importing bookmarks.")
    for b in new:
        aw = Artwork(b)
        artworks[str(aw.id)] = aw.meta
        for i in aw.original_images:
            i.fs_upload()
    artworks.save()

    # Remove bookmarks from the temporary directory
    print(f"Bookmarks imported. Now removing temporary bookmarks.")
    for b in new:
        pixiv.download_cleanup(b)
    print("Successfully refreshed bookmarks.")
    temp["refresh_lock"] = False


@app.route("/display/home", methods=["POST"])
def settings_home():
    if conf["read_only"]:
        flash("<b>Application is read-only.</b> Cannot edit display preferences.", "danger")
        return redirect(url_for("home"))

    # Get settings from post form. These do not need validation as they're reset as needed
    image = request.form.get("image", "original")
    ipp = request.form.get("ipp", "50")
    order = request.form.get("order", "default")
    conf["display"]["home"]["image"] = image
    conf["display"]["home"]["ipp"] = ipp
    conf["display"]["home"]["order"] = order
    conf.save()
    return redirect(url_for("home"))


@app.route("/display/artwork", methods=["POST"])
@app.route("/display/artwork/<r>", methods=["POST"])
def settings_artwork(r=None):
    if conf["read_only"]:
        flash("<b>Application is read-only.</b> Cannot edit display preferences.", "danger")
        if r:
            return redirect(url_for("artwork_show", artwork=r))
        return redirect(url_for("home"))

    # Get setting from post form. It does not require validation as it can be reset as needed
    image = request.form.get("image", "original")
    conf["display"]["artwork"]["image"] = image
    conf.save()
    if r:
        return redirect(url_for("artwork_show", artwork=r))
    return redirect(url_for("home"))  # home redirect should never happen in the first place


@app.route("/display/nsfw/<mode>")
def settings_nsfw(mode):
    r = request.args.get("r", "")
    if r:
        resp = make_response(redirect(r))
        resp.set_cookie("nsfw_state", "true" if mode == "enable" else "false")
        return resp
    resp = make_response(redirect(url_for("home")))
    resp.set_cookie("nsfw_state", "true" if mode == "enable" else "false")
    return resp


@app.route("/a/<artwork>")
@app.route("/a/<artwork>/<image>")
def artwork_show(artwork, image=None):
    _show_nsfw = utils.get_nsfw("artwork")
    _nsfw_pref, _nsfw_user = utils.get_nsfw_state("artwork")
    image = image or conf["display"]["artwork"]["image"]
    if image not in ("original", "large", "medium", "square_medium"):
        flash("<b>Invalid display settings.</b> The image setting was set to <u>original</u>.", "warning")
        image = "original"
    aw = Artwork.from_id(artwork)
    if aw is None:
        flash("<b>Not found.</b> The requested artwork wasn't found locally.", "danger")
        return redirect(url_for("home"))
    return render_template("artwork.html", a=aw,
                           display_config=conf["display"]["artwork"],
                           image=image, display=(aw.nsfw and _show_nsfw) or not aw.nsfw,
                           ro=conf["read_only"], nsfw_master=_nsfw_pref, nsfw=_nsfw_user)


@app.route("/a/<artwork>/pixiv")
def artwork_url(artwork):
    aw = Artwork.from_id(artwork)
    if aw is None:
        flash("<b>Not found.</b> The requested artwork wasn't found locally.", "danger")
        return redirect(url_for("home"))
    return redirect(f"https://www.pixiv.net/artworks/{aw.id}")


@app.route("/a/<artwork>/user-pixiv")
def artwork_user_url(artwork):
    aw = Artwork.from_id(artwork)
    if aw is None:
        flash("<b>Not found.</b> The requested artwork wasn't found locally.", "danger")
        return redirect(url_for("home"))
    return redirect(f"https://www.pixiv.net/users/{aw.user.id}")


@app.route("/a/<artwork>/meta")
def artwork_meta(artwork):
    aw = Artwork.from_id(artwork)
    if aw is None:
        r = Response("{}")
        r.headers['Content-Type'] = 'application/json'
        return r

    # Dump stored metadata to browser as JSON.
    r = Response(dumps(aw.meta, separators=None, indent=None, sort_keys=False))
    r.headers['Content-Type'] = 'application/json'
    return r


@app.route("/a/<artwork>/delete")
def artwork_delete(artwork):
    # Check for blocking states
    if conf["read_only"]:
        flash("<b>Application is read-only.</b> Cannot delete artwork.", "danger")
        return redirect(url_for("home"))
    aw = Artwork.from_id(artwork)
    if aw is None:
        flash("<b>Not found.</b> The requested artwork wasn't found locally.", "danger")
        return redirect(url_for("home"))

    # Start the delete thread
    t = threading.Thread(target=_background_delete, args=(aw,))
    t.start()
    flash(f"<b>Success.</b> Now deleting artwork {aw.id}.", "success")
    return redirect(url_for("home"))


def _background_delete(aw):
    for img in aw.original_images:
        img.fs_delete()
    artworks.pop(str(aw.id))
    artworks.save()


@app.route("/a/<artwork>/pdf")
@app.route("/a/<artwork>/pdf/<quality>")
@app.route("/a/<artwork>/zip")
@app.route("/a/<artwork>/zip/<quality>")
def artwork_download(artwork, quality=None):
    quality = quality or "original"
    mode = request.path.split("/")[3].lower()  # Get third string from path (pdf/zip)
    aw = Artwork.from_id(artwork)
    if aw is None:
        flash("<b>Not found.</b> The requested artwork wasn't found locally.", "danger")
        return redirect(url_for("home"))
    if quality not in ("original", "large", "medium", "square_medium"):
        flash("<b>Unavailable.</b> The requested artwork quality isn't available.", "danger")
        return redirect(url_for("home"))

    # Download/Copy images to memory. Could theoretically cause a OOM kill to happen, shouldn't happen with pixiv
    images = [(i, i.fs_get(quality, force_proxy=True)) for i in aw.original_images]
    if mode == "pdf":
        obj = make_pdf(images)
    elif mode == "zip":
        obj = make_zip(images, quality)
    else:
        obj = None  # Shouldn't happen, but required for the PC linter
    filename = f"{aw.id}_{quality}.{mode}"
    return send_file(obj, as_attachment=True, download_name=filename)


@app.route("/i/<artwork>/<image>")
@app.route("/i/<artwork>/<image>/<quality>")
def artwork_image(artwork, image, quality=None):
    quality = quality or "original"
    aw = Artwork.from_id(artwork)
    if aw is None:
        flash("<b>Not found.</b> The requested artwork wasn't found locally.", "danger")
        return redirect(url_for("home"))
    if quality not in ("original", "large", "medium", "square_medium", "none"):
        flash("<b>Unavailable.</b> The requested artwork quality isn't available.", "danger")
        return redirect(url_for("home"))

    # Return a blank image -- could be improved to return a base64 png.
    if quality == "none":
        return send_file("static/blank.png", as_attachment=False, download_name="blank")
    try:
        if int(image) < 0:
            raise IndexError  # would theoretically work with -1 for last image, but makes no sense
        img = aw.original_images[int(image)]
        obj = img.fs_get(quality)
        if isinstance(obj, str):  # remote storage, no proxy
            return redirect(obj)
        else:  # local storage or remote storage w/proxy
            filename = f"{img.id}_p{img.img}_{quality}.{img.ext}"
            return send_file(obj, as_attachment=False, download_name=filename)
    except (IndexError, ValueError, FileNotFoundError):
        flash("<b>Not found.</b> The requested artwork image wasn't found locally.", "danger")
        return redirect(url_for("home"))


@app.route("/admin", methods=["GET", "POST"])
def admin():
    # The admin view function only exists if the application is set to read_only
    # - it allows the admin or a script to update or delete artworks -
    # as a result, it is not meant to be user-friendly and returns strings instead of html flashes
    if not conf["read_only"]:
        return "Application is read-write."
    if request.method == "GET":
        return render_template("admin.html")

    # Initiates a refresh
    if request.form.get("token_ref"):
        if request.form.get("token_ref").strip() != conf["read_only_token"]:
            return "Invalid token", 403
        if temp.get("refresh_lock", False):
            return "Already refreshing", 400
        t = threading.Thread(target=_background_refresh)
        t.start()
        return "Now refreshing"

    # Initiates an artwork deletion
    if request.form.get("token_del") and request.form.get("artwork"):
        if request.form.get("token_del").strip() != conf["read_only_token"]:
            return "Invalid token", 403
        aw = Artwork.from_id(request.form.get("artwork").strip())
        if aw is None:
            return "Unknown artwork", 404
        t = threading.Thread(target=_background_delete, args=(aw,))
        t.start()
        return "Deleting artwork"


if __name__ == '__main__':
    app.run()
