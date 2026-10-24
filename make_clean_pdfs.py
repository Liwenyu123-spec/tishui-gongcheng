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
order=sorted(byname,key=str.lower); items=[(n,byname[n]) for n in order]
hash_names={n for n in order if re.fullmatch(r'[0-9a-f]{32}\.jpg',n)}

def clean_text(text):
 out=[]; removed=[]
 for line in text.splitlines():
  raw=line.strip()
  if (re.search(r'HONOR\s*80|160MP|Matrix\s*Camera|MatrixC|\bCamera\b|^amera$',raw,re.I)
      or re.fullmatch(r'2026[/-]10[/-]13\s*\d{1,2}:?\d{2}',raw)
      or re.fullmatch(r'2026[/-]10[/-]13\s*\d{1,2}:\d{2}:?\d{0,2}',raw)
      or re.fullmatch(r'2026[/-]10[/-]13\s*\d*',raw)):
   removed.append(raw); continue
  out.append(line)
 return '\n'.join(out).strip(),removed
cleaned={}; removed_rows=[]
for n,t in items:
 c,rm=clean_text(t); cleaned[n]=c
 for x in rm: removed_rows.append((n,x))

pdfmetrics.registerFont(TTFont('SimHei','C:/Windows/Fonts/simhei.ttf'))
styles=getSampleStyleSheet(); title=ParagraphStyle('title',parent=styles['Title'],fontName='SimHei',fontSize=18,leading=24,alignment=TA_CENTER,spaceAfter=12); sub=ParagraphStyle('sub',parent=styles['Heading2'],fontName='SimHei',fontSize=10.5,leading=15,spaceBefore=4,spaceAfter=5); body=ParagraphStyle('body',parent=styles['BodyText'],fontName='SimHei',fontSize=9.2,leading=13.5,spaceAfter=3); small=ParagraphStyle('small',parent=body,fontSize=8,leading=11,textColor='#555555')
def make(path,title_text,selected,desc):
 doc=SimpleDocTemplate(str(path),pagesize=A4,rightMargin=17*mm,leftMargin=17*mm,topMargin=15*mm,bottomMargin=15*mm,title=title_text)
 story=[Paragraph(escape(title_text),title),Paragraph(escape(desc),small),Spacer(1,7)]
 for idx,(name,_) in enumerate(selected,1):
  if idx>1: story.append(PageBreak())
  story.append(Paragraph(f'原图 PDF 第 {order.index(name)+1} 页｜OCR 文件：{escape(name)}',sub))
  lines=[x.strip() for x in cleaned[name].splitlines() if x.strip()] or ['（本页未识别到文字）']
  for line in lines: story.append(Paragraph(escape(line),body))
 def footer(c,d):
  c.saveState(); c.setFont('SimHei',8); c.setFillColorRGB(.35,.35,.35); c.drawCentredString(A4[0]/2,8*mm,f'{title_text}  |  PDF页 {d.page}'); c.restoreState()
 doc.build(story,onFirstPage=footer,onLaterPages=footer)
make(outdir/'二阶段_按原PDF页序_去水印重排版.pdf','二阶段资料（按原 PDF 页序·去水印重排版）',items,'已对照原照片清理照片边缘叠加文字，并按原图片 PDF 页序重新排版。')
make(outdir/'工程资料_去水印重排版.pdf','工程资料（去水印重排版）',[(n,byname[n]) for n in order if n in hash_names],'已去除相机水印，并按原图片 PDF 页序排列。')
make(outdir/'提水泵站规程_去水印重排版.pdf','提水泵站规程（去水印重排版）',[(n,byname[n]) for n in order if n not in hash_names],'已去除相机水印，并按原图片 PDF 页序排列。')
with (outdir/'二阶段_已删除水印清单.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f); w.writerow(['原图PDF页码','图片文件名','删除的水印文字'])
 for n,x in removed_rows: w.writerow([order.index(n)+1,n,x])
print('blocks',len(items),'removed',len(removed_rows))


