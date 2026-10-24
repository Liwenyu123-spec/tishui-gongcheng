from pathlib import Path
import re,csv
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
src=Path('D:/图片转成的pdf/[OCR]_图片_20261024_0939.txt'); outdir=Path('D:/图片转成的pdf')
s=src.read_text(encoding='utf-8',errors='replace'); parts=re.split(r'≦\s*([^≧]+?)\s*≧',s)
byname={}
for i in range(1,len(parts),2): byname[parts[i].strip()]=parts[i+1].strip()
order=sorted(byname,key=str.lower)
items=[(n,byname[n]) for n in order]
hash_items=[x for x in items if re.fullmatch(r'[0-9a-f]{32}\.jpg',x[0])]
img_items=[x for x in items if x[0].startswith('IMG_')]
pdfmetrics.registerFont(TTFont('SimHei','C:/Windows/Fonts/simhei.ttf'))
styles=getSampleStyleSheet(); title=ParagraphStyle('title',parent=styles['Title'],fontName='SimHei',fontSize=18,leading=24,alignment=TA_CENTER,spaceAfter=12); sub=ParagraphStyle('sub',parent=styles['Heading2'],fontName='SimHei',fontSize=10.5,leading=15,spaceBefore=4,spaceAfter=5); body=ParagraphStyle('body',parent=styles['BodyText'],fontName='SimHei',fontSize=9.2,leading=13.5,spaceAfter=3); small=ParagraphStyle('small',parent=body,fontSize=8,leading=11,textColor='#555555')
def make(path,title_text,items,desc):
 doc=SimpleDocTemplate(str(path),pagesize=A4,rightMargin=17*mm,leftMargin=17*mm,topMargin=15*mm,bottomMargin=15*mm,title=title_text)
 story=[Paragraph(escape(title_text),title),Paragraph(escape(desc),small),Spacer(1,7)]
 for idx,(name,text) in enumerate(items,1):
  if idx>1: story.append(PageBreak())
  story.append(Paragraph(f'原图 PDF 第 {order.index(name)+1} 页｜OCR 文件：{escape(name)}',sub))
  lines=[x.strip() for x in text.splitlines() if x.strip()] or ['（本页未识别到文字）']
  for line in lines: story.append(Paragraph(escape(line),body))
 def footer(c,d):
  c.saveState(); c.setFont('SimHei',8); c.setFillColorRGB(.35,.35,.35); c.drawCentredString(A4[0]/2,8*mm,f'{title_text}  |  PDF页 {d.page}'); c.restoreState()
 doc.build(story,onFirstPage=footer,onLaterPages=footer)
make(outdir/'二阶段_按原PDF页序_文字校对版.pdf','二阶段资料（按原 PDF 页序校对版）',items,'以二阶段图片合集.pdf 的 186 页顺序为基准，将 OCR 文字重新对齐；每页保留原图片文件名以便核对。')
make(outdir/'工程资料_按原PDF页序_校对版.pdf','工程资料（按原 PDF 页序校对版）',hash_items,'哈希文件名图片组；已按原图片 PDF 的文件名页序重新排列。')
make(outdir/'提水泵站规程_按原PDF页序_校对版.pdf','提水泵站规程（按原 PDF 页序校对版）',img_items,'IMG 文件名图片组；已按原图片 PDF 的文件名页序重新排列。')
with (outdir/'二阶段_OCR校对清单.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f); w.writerow(['原PDF页码','图片文件名','资料分组','OCR字符数','空白行数'])
 for i,n in enumerate(order,1):
  t=byname[n]; w.writerow([i,n,'工程资料' if n in dict(hash_items) else '提水泵站规程',len(t),sum(1 for x in t.splitlines() if not x.strip())])
print('aligned',len(items),len(hash_items),len(img_items))
