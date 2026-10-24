from pathlib import Path
import re
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

src=Path('D:/图片转成的pdf/[OCR]_图片_20261024_0939.txt')
outdir=Path('D:/图片转成的pdf')
s=s=src.read_text(encoding='utf-8',errors='replace')
parts=re.split(r'≦\s*([^≧]+?)\s*≧',s)
blocks=[]
for i in range(1,len(parts),2):
    name=parts[i].strip(); text=parts[i+1].strip()
    blocks.append((name,text))
hash_blocks=[b for b in blocks if re.fullmatch(r'[0-9a-f]{32}\.jpg',b[0])]
img_blocks=[b for b in blocks if b[0].startswith('IMG_')]
pdfmetrics.registerFont(TTFont('SimHei','C:/Windows/Fonts/simhei.ttf'))
styles=getSampleStyleSheet()
title=ParagraphStyle('title',parent=styles['Title'],fontName='SimHei',fontSize=18,leading=24,alignment=TA_CENTER,spaceAfter=12)
sub=ParagraphStyle('sub',parent=styles['Heading2'],fontName='SimHei',fontSize=11,leading=16,spaceBefore=4,spaceAfter=6)
body=ParagraphStyle('body',parent=styles['BodyText'],fontName='SimHei',fontSize=9.5,leading=14,spaceAfter=4)
small=ParagraphStyle('small',parent=body,fontSize=8,leading=11,textColor='#555555')

def make_pdf(path,title_text,items,desc):
    doc=SimpleDocTemplate(str(path),pagesize=A4,rightMargin=18*mm,leftMargin=18*mm,topMargin=16*mm,bottomMargin=16*mm,title=title_text)
    story=[Paragraph(escape(title_text),title),Paragraph(escape(desc),small),Spacer(1,8)]
    for idx,(name,text) in enumerate(items,1):
        if idx>1: story.append(PageBreak())
        story.append(Paragraph(f'第 {idx} 个 OCR 页面：{escape(name)}',sub))
        lines=[x.strip() for x in text.splitlines() if x.strip()]
        if not lines: lines=['（本页未识别到文字）']
        for line in lines:
            story.append(Paragraph(escape(line),body))
    def footer(canvas,doc):
        canvas.saveState(); canvas.setFont('SimHei',8); canvas.setFillColorRGB(.35,.35,.35); canvas.drawCentredString(A4[0]/2,9*mm,f'{title_text}  |  PDF页 {doc.page}'); canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)

make_pdf(outdir/'工程资料_文字识别.pdf','工程资料（OCR文字版）',hash_blocks,'来源：38张哈希文件名图片；内容主要涉及工程设计数据、泉群/管道/倒虹吸资料及第七章生产管理。')
make_pdf(outdir/'提水泵站规程_文字识别.pdf','提水泵站运行维护规程（OCR文字版）',img_blocks,'来源：148张IMG图片；内容主要涉及泵站运行、设备操作、维护检修、安全管理和事故处理章节。')
print('created',len(hash_blocks),len(img_blocks))
