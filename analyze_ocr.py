from pathlib import Path
import re
p=Path('D:/图片转成的pdf/[OCR]_图片_20261024_0939.txt')
s=p.read_text(encoding='utf-8',errors='replace')
blocks=re.split(r'≦\s*([^≧]+?)\s*≧',s)
print('blocks',(len(blocks)-1)//2)
heads=[]
for i in range(1,len(blocks),2):
 name=blocks[i].strip(); text=blocks[i+1]
 lines=[x.strip() for x in text.splitlines() if re.search(r'第.{0,3}[章节]|目录|序言|前言|附录|表[0-9]',x)]
 if lines: heads.append((name,' | '.join(lines)[:300]))
print('head blocks',len(heads))
for h in heads: print('---',h[0],h[1])
