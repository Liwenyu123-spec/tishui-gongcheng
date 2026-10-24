from pathlib import Path
import re,json
s=Path(r'D:\图片转成的pdf\[OCR]_图片_20261024_0939.txt').read_text(encoding='utf-8',errors='replace')
p=re.split(r'≦\s*([^≧]+?)\s*≧',s)
for i in range(1,len(p),2):
 n=p[i].strip(); t=p[i+1]
 if len(n)==36 or n.startswith('IMG_'):
  lines=[x.strip() for x in t.splitlines() if x.strip()]
  ds=[]
  for j,l in enumerate(lines):
   nums=re.findall(r'(?<!\d)\d{1,3}(?!\d)',l)
   if nums: ds.append((j,nums,l[:120]))
  print(n, 'LINES',len(lines), 'LAST')
  for l in lines[-8:]: print(repr(l[:180]))
  print('DIGITS',ds[-20:])
