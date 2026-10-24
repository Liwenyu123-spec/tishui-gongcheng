from pathlib import Path
import re,sys
sys.stdout.reconfigure(encoding='utf-8')
s=Path(r'D:\图片转成的pdf\[OCR]_图片_20261024_0939.txt').read_text(encoding='utf-8',errors='replace')
p=re.split(r'≦\s*([^≧]+?)\s*≧',s)
for i in range(1,len(p),2):
 n=p[i].strip(); t=p[i+1]
 if n.startswith('IMG_'):
  lines=[x.strip() for x in t.splitlines() if x.strip()]
  cand=[]
  for l in lines[:8]:
   m=re.search(r'(?<!\d)(\d{1,3})\s*[·。.]',l)
   if m: cand.append(m.group(1))
   m2=re.match(r'^\D{0,3}(\d{1,3})\D',l)
   if m2: cand.append(m2.group(1))
  print(n, cand[:3], '|', ' / '.join(lines[:2]))
