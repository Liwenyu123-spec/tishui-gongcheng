import fitz
from PIL import Image
from pathlib import Path
pdf=fitz.open(r'D:/图片转成的pdf/二阶段图片合集.pdf')
for i in [0,1,2,3,4,30,31,100,185]:
 p=pdf[i]; pix=p.get_pixmap(matrix=fitz.Matrix(.25,.25),alpha=False); pix.save(fr'tmp/pdfp{i+1}.jpg')
 print(i+1,p.rect)
