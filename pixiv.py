import requests
from pathlib import Path
from shutil import rmtree

import pixivpy3
from urllib import parse

from pxyTools import JSONDict

from utils import conf

PATH = Path(conf["temp_path"])

app_api = pixivpy3.aapi.AppPixivAPI()


def auth():
    # Authenticate with pixiv and get a new access/refresh token
    login = app_api.auth(refresh_token=conf["pixiv"]["refresh"])
    conf["pixiv"]["access"] = login["access_token"]
    conf["pixiv"]["refresh"] = login["refresh_token"]
    conf.save()
    return login


def get_bookmarks():
    login = auth()
    illustrations = []
    index = None
    print("Fetching bookmarks...")
    # pixiv bookmarks works with a max_bookmark_id, which acts as a "depth" in the bookmarks
    while True:
        print(f"current depth: {index}")
        r = app_api.user_bookmarks_illust(login["user"]["id"], max_bookmark_id=index)  # query pixiv for bookmarks
        illustrations += r["illusts"]
        try:
            # noinspection PyTypeChecker
            index = parse.parse_qs(parse.urlparse(r["next_url"]).query)["max_bookmark_id"][0]  # get new depth value
        except (IndexError, KeyError):
            break
    print(f"Fetched {len(illustrations)} bookmarks.")
    return illustrations


def download_bookmarks(illustration):
    iid = illustration["id"]
    cur = 0
    queue = []
    # Enqueues images in the metadata.
    if illustration["meta_single_page"]:
        queue.append((illustration["meta_single_page"]["original_image_url"], f"{iid}_p{cur}_original"))
        # Gets previews from image_urls as they aren't included in meta_single_page
        queue.append((illustration["image_urls"]["large"], f"{iid}_p{cur}_large"))
        queue.append((illustration["image_urls"]["medium"], f"{iid}_p{cur}_medium"))
        queue.append((illustration["image_urls"]["square_medium"], f"{iid}_p{cur}_square_medium"))
    for p in illustration["meta_pages"]:
        queue.append((p["image_urls"]["original"], f"{iid}_p{cur}_original"))
        queue.append((p["image_urls"]["large"], f"{iid}_p{cur}_large"))
        queue.append((p["image_urls"]["medium"], f"{iid}_p{cur}_medium"))
        queue.append((p["image_urls"]["square_medium"], f"{iid}_p{cur}_square_medium"))
        cur += 1
    mp = Path(f"{PATH}/{iid}")
    mp.mkdir(exist_ok=True)

    for url, filename in queue:
        # Get the extension based of the end of the URL
        ext = str(parse.urlparse(url).path).split("/")[-1].split(".")[-1]
        # Setting the Referer header is mandatory for the pixivCDN
        with requests.get(url, headers={'Referer': url}) as r:
            if r.ok:
                Path(f"{mp}/{filename}.{ext}").write_bytes(r.content)
            print(f"queue: {mp}/{filename} - {len(r.content)}B in {int(r.elapsed.microseconds/1000)}ms ->"
                  f" {r.status_code}")
    JSONDict(f"{mp}/_meta.json", data=illustration).save()  # This isn't used anymore, but is still saved in case...


def download_cleanup(illustration):
    iid = illustration["id"]
    mp = Path(f"{PATH}/{iid}")
    rmtree(mp, True)
