from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PIL import Image
from pathlib import Path
src=Path('H:/二阶段/图片')
out=Path('D:/图片转成的pdf/二阶段图片合集.pdf')
files=sorted(src.glob('*.jpg'), key=lambda p:p.name.lower())
c=None
scale=2.0
for p in files:
    im=Image.open(p)
    w,h=im.size
    pw,ph=w/scale,h/scale
    if c is None:
        c=canvas.Canvas(str(out), pagesize=(pw,ph), pageCompression=1)
    else:
        c.setPageSize((pw,ph))
    c.drawImage(ImageReader(str(p)),0,0,width=pw,height=ph,mask='auto')
    c.showPage()
c.save()
print(len(files), out, out.stat().st_size)
