from datetime import datetime
import timeago

import requests
from pathlib import Path
from shutil import copyfile
from urllib import parse
from io import BytesIO

from utils import conf, artworks, now_tz

from .user import User


class Artwork:
    def __init__(self, meta):
        self.id = meta["id"]

        self.title = meta["title"]
        self.caption = meta["caption"]

        self.user = User(meta)

        self.preview = OriginalArtworkImage(0, meta)

        self.nsfw_level = meta["x_restrict"]
        self.nsfw = self.nsfw_level > 0

        self.tags = [ArtworkTag(x) for x in meta["tags"]]
        self.tools = meta["tools"]
        self.width = meta["width"]
        self.height = meta["height"]

        self.post_date = datetime.strptime(meta["create_date"], "%Y-%m-%dT%H:%M:%S%z")
        self.post_date_ago = timeago.format(self.post_date, now_tz())

        self.page_count = meta["page_count"]

        self.sanity_level = meta["sanity_level"]
        self.restrict = meta["restrict"]
        self.type = meta["type"]

        self.views = meta["total_view"]
        self.bookmarks = meta["total_bookmarks"]

        self.meta = meta

        if meta["meta_pages"]:
            self.original_images = [OriginalArtworkImage(x, meta) for x in range(len(meta["meta_pages"]))]
        else:
            self.original_images = [OriginalArtworkImage(0, meta)]

    @classmethod
    def from_id(cls, aid):
        if str(aid) in artworks:
            return cls(artworks[str(aid)])
        return None

    @classmethod
    def all(cls, limit=0, offset=0):
        aws = list(artworks.keys())  # this allows to select only a subset of artworks
        aws.reverse()
        if not limit:
            return [cls(artworks[a]) for a in aws]
        return [cls(artworks[a]) for a in aws[offset:offset+limit]]

    @classmethod
    def all_filtered(cls, limit=0, offset=0):
        aws = [k for k, v in artworks.items() if v["x_restrict"] <= 0]  # filter artworks when creating keys list
        aws.reverse()
        if not limit:
            return [cls(artworks[a]) for a in aws]
        return [cls(artworks[a]) for a in aws[offset:offset+limit]]


class ArtworkTag:
    def __init__(self, tag_meta):
        self.name = tag_meta["name"]
        self.translated_name = tag_meta["translated_name"]


class OriginalArtworkImage:
    def __init__(self, img, meta):
        if meta["meta_pages"]:
            self.original = meta["meta_pages"][img]["image_urls"]["original"]
            self.large = meta["meta_pages"][img]["image_urls"]["large"]
            self.medium = meta["meta_pages"][img]["image_urls"]["medium"]
            self.square_medium = meta["meta_pages"][img]["image_urls"]["square_medium"]
        else:
            self.original = meta["meta_single_page"]["original_image_url"]
            self.large = meta["image_urls"]["large"]
            self.medium = meta["image_urls"]["medium"]
            self.square_medium = meta["image_urls"]["square_medium"]
        self.id = meta["id"]
        self.img = img
        # the following image extension is only valid for the full size image, large/medium/square are always jpeg.
        # get_ext() will always return the correct extension using the code below, for the correct image quality
        self.ext = str(parse.urlparse(self.original).path).split("/")[-1].split(".")[-1]

    def fs_upload(self):
        for x in ("original", "large", "medium", "square_medium"):
            filename = f"{self.id}_p{self.img}_{x}.{self.get_ext(x)}"
            assert Path(f"{conf['temp_path']}/{self.id}/{filename}").exists()  # kill the import if download failure
        for x in ("original", "large", "medium", "square_medium"):
            filename = f"{self.id}_p{self.img}_{x}.{self.get_ext(x)}"
            source = Path(f"{conf['temp_path']}/{self.id}/{filename}")
            if conf["filesystem"] == "local":
                dest = Path(f"{conf['filesystem_options']['path']}/{self.id}/{filename}")
                dest.parent.mkdir(exist_ok=True)
                copyfile(source, dest)
                print(f"copy: {self.id}/{filename}")
            elif conf["filesystem"] == "remote":
                with source.open('rb') as s:
                    # the remote filesystem is only compatible with php-fs. if using ftp/sftp/rsync/whatever mount,
                    # the user should use local and specify the path to the mount
                    r = requests.post(f"{conf['filesystem_options']['server']}/upload",
                                      headers={"Token": conf["filesystem_options"]["token"]},
                                      data={"path": self.id, "file": filename},
                                      files={"file": s})
                    print(f"upload: {self.id}/{filename} - {int(r.elapsed.microseconds/1000)}ms {r.status_code}")
                    if not r.ok:
                        print(f"Upload failure for {self.id}/{filename}.")

    def fs_delete(self):
        for x in ("original", "large", "medium", "square_medium"):
            filename = f"{self.id}_p{self.img}_{x}.{self.get_ext(x)}"
            if conf["filesystem"] == "local":
                target = Path(f"{conf['filesystem_options']['path']}/{self.id}/{filename}")
                target.unlink(missing_ok=True)
                print(f"delete: {self.id}/{filename}")
            elif conf["filesystem"] == "remote":
                r = requests.post(f"{conf['filesystem_options']['server']}/delete",
                                  headers={"Token": conf["filesystem_options"]["token"]},
                                  data={"path": self.id, "file": filename})
                print(f"delete: {self.id}/{filename} - {int(r.elapsed.microseconds/1000)}ms {r.status_code}")
                if not r.ok:
                    print(f"Delete failure for {self.id}/{filename}.")

    def fs_get(self, quality, force_proxy=False):
        assert quality in ("original", "large", "medium", "square_medium")
        filename = f"{self.id}_p{self.img}_{quality}.{self.get_ext(quality)}"
        if conf["filesystem"] == "local":
            return Path(f"{conf['filesystem_options']['path']}/{self.id}/{filename}").open('rb')
        elif conf["filesystem"] == "remote":
            url = f"{conf['filesystem_options']['server']}/{self.id}/{filename}"
            if conf["filesystem_options"]["proxy"] or force_proxy:
                r = requests.get(url)
                return BytesIO(r.content)  # make it a readable file-like object
            else:
                return url

    def get_url(self, quality):
        assert quality in ("original", "large", "medium", "square_medium")
        return self.__getattribute__(quality)

    def get_ext(self, quality):
        return str(parse.urlparse(self.get_url(quality)).path).split("/")[-1].split(".")[-1]
