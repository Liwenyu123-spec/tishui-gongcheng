from pathlib import Path
import re
s=Path('D:/图片转成的pdf/[OCR]_图片_20261024_0939.txt').read_text(encoding='utf-8',errors='replace')
parts=re.split(r'≦\s*([^≧]+?)\s*≧',s)
names={'06f5fb5111407012c784c9b299befba7.jpg','IMG_20261023_192839.jpg','IMG_20261023_200927.jpg'}
for i in range(1,len(parts),2):
 if parts[i].strip() in names:
  print('---',parts[i].strip()); print('\n'.join(parts[i+1].splitlines()[-20:]))
