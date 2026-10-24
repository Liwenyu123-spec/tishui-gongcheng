from pathlib import Path
import re
s=Path('D:/图片转成的pdf/[OCR]_图片_20261024_0939.txt').read_text(encoding='utf-8',errors='replace')
p=re.split(r'≦\s*([^≧]+?)\s*≧',s)
for i in range(1,len(p),2):
 n=p[i].strip();
 if len(n)==36 and n.endswith('.jpg'):
  lines=[x.strip() for x in p[i+1].splitlines() if x.strip()]
  nums=[]
  for x in lines[-15:]:
   if re.fullmatch(r'[·.。]?\s*\d{1,3}\s*[·.。]?',x): nums.append(x)
  print(n[:8], ' | '.join(lines[-8:]), ' || nums=',nums)
