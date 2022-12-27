from flask import flash as orig_flash, Markup, request
from datetime import datetime, timezone, timedelta

from pxyTools import JSONDict

conf = JSONDict("config.json")
artworks = JSONDict("artworks.json")
temp = JSONDict("temp.json")


def flash(message, category):
    return orig_flash(Markup(message), category)


def update_metadata(aws):
    for aw in aws:
        # Passes if artwork isn't stored, has limit flags or restrict other than zero
        if str(aw["id"]) not in artworks:
            print(f"Metadata not found on disk for Artwork {aw['id']}")
            continue
        if any(x in str(aw) for x in ("limit_unknown_360", "limit_mypixiv_360")):
            print(f"Avoided possible pixiv deletion for Artwork {aw['id']} (has limit)")
            continue
        if aw["restrict"] != 0:
            print(f"Avoided possible pixiv deletion for Artwork {aw['id']} (restrict != 0)")
            continue
        # Update metadata for artwork
        artworks[str(aw["id"])] = aw


def filter_artworks(aws):
    new = []
    for i in aws:
        # Passes if artwork has limit flags, restrict other than zero or is animated (video/gif)
        if any(x in str(i) for x in ("limit_unknown_360", "limit_mypixiv_360")):
            print(f"Not adding possible deleted pixiv Artwork {i['id']} (has limit)")
            continue
        if i["restrict"] != 0:
            print(f"Not adding possible deleted pixiv Artwork {i['id']} (restrict != 0)")
            continue
        if "ugoira" in str(i):
            print(f"Not adding unsupported pixiv Artwork {i['id']} (ugoira)")
            continue
        if str(i["id"]) not in artworks:
            new.append(i)
    return new


def gen_paginate_data(current, pages, base_path, margin=2,
                      prev_btn=True, next_btn=True,
                      first_btn=True, last_btn=True):
    to_gen = []
    for i in reversed(range(1, margin+1)):
        if current - i <= 0:
            continue
        to_gen.append(current - i)
    to_gen.append(current)
    for i in range(1, margin+1):
        if current + i > pages:
            continue
        to_gen.append(current + i)
    d = []
    if prev_btn:
        if current - 1 > 0:
            d.append(("«", base_path.format(current - 1), ""))
        else:
            d.append(("«", "#", "disabled"))
    if first_btn:
        if 1 not in to_gen:
            d.append((1, base_path.format(1), ""))
            d.append(("...", "#", "disabled"))
    for p in to_gen:
        if p == current:
            d.append((p, base_path.format(p), "active"))
            continue
        d.append((p, base_path.format(p), ""))
    if last_btn:
        if pages not in to_gen:
            d.append(("...", "#", "disabled"))
            d.append((pages, base_path.format(pages), ""))
    if next_btn:
        if current + 1 <= pages:
            d.append(("»", base_path.format(current + 1), ""))
        else:
            d.append(("»", "#", "disabled"))
    return d


def now_tz():
    # Determines the UTC offset based on local time
    offset = round((datetime.now() - datetime.utcnow()).seconds/3600)
    tzdata = timezone(timedelta(hours=offset))
    return datetime.now(tzdata)


def get_nsfw(page):
    pref = conf["display"]["nsfw"]
    user = request.cookies.get("nsfw_state", "false") == "true"

    # NSFW is enabled on home+artwork, ignoring the user choice
    if pref == "enabled":
        return True
    # NSFW is required to be user-enabled on all pages
    elif pref == "required":
        return user
    # NSFW is required to be user-enabled for it to show on the homepage
    elif pref == "hidden":
        if page == "home":
            return user
        else:
            return True
    # NSFW is disabled on home+artwork, ignoring the user choice
    else:
        return False


def get_nsfw_state(page):
    pref = conf["display"]["nsfw"]
    user = request.cookies.get("nsfw_state", "false") == "true"
    if page == "home":
        return pref in ("required", "hidden"), user
    else:
        return pref == "required", user
