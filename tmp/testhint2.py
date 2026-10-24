exec(open('make_page_ordered_pdfs.py',encoding='utf-8').read().split("make_pdf(OUT/")[0])
for n in ['IMG_20261023_193034.jpg','IMG_20261023_193018.jpg','IMG_20261023_193051.jpg','IMG_20261023_193103.jpg']:
 print(n,img_page_hint(byname[n]))
