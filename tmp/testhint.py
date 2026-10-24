exec(open('make_page_ordered_pdfs.py',encoding='utf-8').read().split("make_pdf(OUT/")[0])
import sys; sys.stdout.reconfigure(encoding='utf-8')
for n in ['IMG_20261023_193034.jpg','IMG_20261023_193018.jpg','IMG_20261023_193051.jpg']:
 print(n,img_page_hint(byname[n]))
 for l in (byname[n].splitlines()[:16]+byname[n].splitlines()[-16:]):
  if '·' in l or '。' in l or re.match(r'^\s*\d',l): print(repr(l))
