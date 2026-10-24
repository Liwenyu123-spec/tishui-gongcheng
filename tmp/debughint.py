exec(open('make_page_ordered_pdfs.py',encoding='utf-8').read().split("make_pdf(OUT/")[0])
import sys;sys.stdout.reconfigure(encoding='utf-8')
for n in ['IMG_20261023_192952.jpg','IMG_20261023_193116.jpg','IMG_20261023_193326.jpg']:
 print('\n',n,img_page_hint(byname[n]))
 for l in byname[n].splitlines()[:16]+byname[n].splitlines()[-16:]:
  if '规程' in l or '·' in l or '。' in l: print(repr(l))
