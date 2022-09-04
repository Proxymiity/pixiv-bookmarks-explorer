from io import BytesIO

from typing import Tuple
from objects import OriginalArtworkImage

import img2pdf
from PIL import Image

from zipfile import ZipFile, ZIP_BZIP2

img2pdf_exceptions = (img2pdf.UnsupportedColorspaceError, img2pdf.JpegColorspaceError,
                      img2pdf.AlphaChannelError, img2pdf.ImageOpenError, img2pdf.PdfTooLargeError)


def make_pdf(images: list[Tuple[OriginalArtworkImage, BytesIO]]):
    obj = BytesIO()
    # Strip OriginalArtworkImage metadata from list, return only BytesIOs
    files = [x[1] for x in images]
    try:  # Try a direct conversion. May not always be successful because of alpha channels
        obj.write(img2pdf.convert(files))
    except img2pdf_exceptions:
        t_files = convert_images(files)  # Convert images to standard JPEG and retry
        obj.write(img2pdf.convert(t_files))
    obj.seek(0)  # Seeks the BytesIO object to 0 as flask reads from the current pointer position
    return obj


def convert_images(source):
    t_files = []
    for i in source:
        fg = Image.open(i)
        if fg.mode in ("P", "RGBA", "LA", "PA"):  # Usually indicates a problematic PNG image with alpha channels
            fg.load()
            bg = Image.new("RGB", fg.size, (255, 255, 255))
            try:
                bg.paste(fg, mask=fg.split()[3])
            except IndexError:
                bg.paste(fg)
            obj = BytesIO()
            bg.save(obj, "JPEG", quality=100)
            t_files.append(obj)
        else:
            t_files.append(i)
    return t_files


def make_zip(images: list[Tuple[OriginalArtworkImage, BytesIO]], quality):
    obj = BytesIO()
    # Read BytesIO and drop them in the archive
    with ZipFile(obj, 'w', ZIP_BZIP2) as d:
        for i, o in images:
            d.writestr(f"{i.id}_p{i.img}_{quality}.{i.get_ext(quality)}", o.read())
    obj.seek(0)  # Seeks the BytesIO object to 0 as flask reads from the current pointer position
    return obj
