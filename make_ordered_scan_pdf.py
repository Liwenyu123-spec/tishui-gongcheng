from pathlib import Path
from io import BytesIO
import runpy, shutil
from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

BASE = Path(r'H:/Python工程/提水工程项目')
OUT = BASE / 'tmp' / 'final_pdfs'
OUT.mkdir(parents=True, exist_ok=True)
ns = runpy.run_path(str(BASE / 'make_page_ordered_pdfs.py'))
IMGDIR = ns['IMGDIR']; byname = ns['byname']; img_names = ns['img_names']; img_page_hint = ns['img_page_hint']
HASH_PAGE = ns['HASH_PAGE']; hash_names = ns['hash_names']
pdfmetrics.registerFont(TTFont('SimHei', r'C:/Windows/Fonts/simhei.ttf'))

def clean_hash(im):
    # Remove the two phone watermark blocks from the bottom edge.  Printed page
    # numbers sit above this strip, so no book text is removed.
    im = im.copy().convert('RGB')
    d = ImageDraw.Draw(im)
    w, h = im.size
    y = int(h * .935)
    d.rectangle((0, y, int(w*.58), h), fill='white')
    d.rectangle((int(w*.67), y, w, h), fill='white')
    return im

def put_page(c, im, label):
    # 150 dpi is sufficient for A4 reading and keeps the many-page result
    # manageable.  The original files remain untouched in the source folder.
    max_dim = 1600
    if max(im.size) > max_dim:
        ratio = max_dim / max(im.size)
        im = im.resize((int(im.width*ratio), int(im.height*ratio)), Image.Resampling.LANCZOS)
    bio = BytesIO(); im.save(bio, format='JPEG', quality=76, optimize=True); bio.seek(0)
    iw, ih = im.size; pw, ph = A4
    maxw, maxh = pw-18*mm, ph-22*mm
    scale = min(maxw/iw, maxh/ih)
    dw, dh = iw*scale, ih*scale
    x, y = (pw-dw)/2, 13*mm + (maxh-dh)/2
    c.drawImage(ImageReader(bio), x, y, dw, dh, preserveAspectRatio=True, mask='auto')
    c.setFont('SimHei', 7.5); c.setFillColorRGB(.3,.3,.3)
    c.drawCentredString(pw/2, 7*mm, label)
    c.showPage()

def make_engineering(path):
    c = canvas.Canvas(str(path), pagesize=A4, pageCompression=1)
    c.setTitle('工程资料（按印刷页码图文版）')
    for n in hash_names:
        im = clean_hash(Image.open(IMGDIR/n))
        put_page(c, im, f'工程资料 | 原图印刷页码 {HASH_PAGE[n]} | {n}')
    c.save()

def make_pump(path):
    c = canvas.Canvas(str(path), pagesize=A4, pageCompression=1)
    c.setTitle('提水泵站规程（按原图页序拆分图文版）')
    for i, n in enumerate(img_names, 1):
        im = Image.open(IMGDIR/n).convert('RGB')
        hint = img_page_hint(byname[n])
        w, h = im.size
        if i == 1 and h >= w:
            # The first photo contains the opening page on the right and an
            # unrelated preceding page on the left; retain the opening page.
            crop = im.crop((int(w*.08), 0, int(w*.96), h))
            put_page(c, crop, f'提水泵站规程 | 印刷页码 {hint or 1} | 原图 {i:03d} | {n}')
            continue
        if w > h:
            mid = w//2
            left = im.crop((0, 0, mid, h))
            right = im.crop((mid, 0, w, h))
            lp = hint if hint is not None else None
            rp = hint+1 if hint is not None else None
            put_page(c, left, f'提水泵站规程 | 印刷页码 {lp or "按原图连续顺序"} | 原图 {i:03d} 左页 | {n}')
            put_page(c, right, f'提水泵站规程 | 印刷页码 {rp or "按原图连续顺序"} | 原图 {i:03d} 右页 | {n}')
        else:
            put_page(c, im, f'提水泵站规程 | 按原图连续顺序 | 原图 {i:03d} | {n}')
    c.save()

make_engineering(OUT/'工程资料_按印刷页码_图文拆页版.pdf')
make_pump(OUT/'提水泵站规程_按原图页序_图文拆页版.pdf')
print('created scan PDFs')
