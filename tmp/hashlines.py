from pathlib import Path
import re,sys
sys.stdout.reconfigure(encoding='utf-8')
s=Path(r'D:\图片转成的pdf\[OCR]_图片_20261024_0939.txt').read_text(encoding='utf-8',errors='replace')
p=re.split(r'≦\s*([^≧]+?)\s*≧',s)
for i in range(1,len(p),2):
 n=p[i].strip(); t=p[i+1]
 if len(n)==36:
  lines=[x.strip() for x in t.splitlines() if x.strip()]
  print('\n###',n)
  for j,l in enumerate(lines):
   if any(ch.isdigit() for ch in l) and len(l)<120:
    print(j,repr(l))
