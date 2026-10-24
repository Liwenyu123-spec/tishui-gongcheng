exec(open('make_page_ordered_pdfs.py',encoding='utf-8').read().split("make_pdf(OUT/")[0])
import sys;sys.stdout.reconfigure(encoding='utf-8')
for l in byname['IMG_20261023_193103.jpg'].splitlines()[:16]+byname['IMG_20261023_193103.jpg'].splitlines()[-16:]:
 print(repr(l))
