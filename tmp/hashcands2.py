from pathlib import Path
import re,sys
sys.stdout.reconfigure(encoding='utf-8')
s=Path(r'D:\图片转成的pdf\[OCR]_图片_20261024_0939.txt').read_text(encoding='utf-8',errors='replace')
p=re.split(r'≦\s*([^≧]+?)\s*≧',s)
for i in range(1,len(p),2):
 n=p[i].strip(); t=p[i+1]
 if len(n)==36:
  lines=[x.strip() for x in t.splitlines() if x.strip()]
  found=[]
  for j,l in enumerate(lines):
   for m in re.finditer(r'[·。.]\s*(\d{2,3})\s*[·。.]?|(?<!\d)(\d{2,3})\s*[·。.]',l):
    v=m.group(1) or m.group(2)
    if v not in ['160','202','199','200','201','380','500','600','750','900','985','1000','1050','1100','1200','1300','1400','1500','1600','1700','1800','1900','2000']:
     found.append((j,v,l))
  print(n[:8], found[-3:])
