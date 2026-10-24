from pathlib import Path
import re, csv, shutil
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

OCR = Path(r'D:/图片转成的pdf/[OCR]_图片_20261024_0939.txt')
IMGDIR = Path(r'H:/二阶段/图片')
OUT = Path(r'H:/Python工程/提水工程项目/tmp/final_pdfs')
OUT.mkdir(parents=True, exist_ok=True)

# These page numbers were read from the printed page footer/header in the photos.
# 9cb... is inferred as page 38 from the surrounding printed pages 37 and 39;
# all other values are directly visible in the page or its OCR footer.
HASH_PAGE = {
    'c528353c3869d5c8a66417f23102d2fc.jpg':31,
    '25fa8995ae7f9cb1c23781f2cbea2570.jpg':32,
    '399a753262487eee8f42442d659d093c.jpg':33,
    '6aa178184bbe34c34d13ed4d55fbec28.jpg':34,
    '4550ad2e346b9a8bd97c323a2a16c832.jpg':35,
    '806a62af5e01f11a1a67c3a09bec8ce7.jpg':36,
    'c5a2cdec7f9ab120ce6aa58c5af1ea14.jpg':37,
    '9cbff1c753aeca2a27421a04d7a8fdbc.jpg':38,
    '2b0a002b66aa2e5633108277f65c8cc0.jpg':39,
    '60adcc7c0c6864fa4ae8a8cc55da4bfe.jpg':40,
    '9e87dfe60a04373e731f51d30eb6b90a.jpg':41,
    '4af26771e46094eacfe12df05d8e6e47.jpg':42,
    'a1a2a852f47c3e145aac0f71838da31d.jpg':43,
    '3d2ea67483aea6ca3a801cc3d3f52b89.jpg':44,
    '6fc6ab16cdedfbd8642eea75b8203a9f.jpg':45,
    'a671050810ce24247662e0a79e7028e8.jpg':46,
    '259034e30d0a80be5e07d4e8923b7add.jpg':47,
    '91704b95c0b04a6d3706124aedf0bf3e.jpg':89,
    'e4d4989b7e11836cf18e43b394fedf84.jpg':90,
    'f7b891598239153be1109e13f399c425.jpg':91,
    '83f30ba20ea90a2ea7f718d9cc720743.jpg':92,
    '13b81475633df6f238da56b53dccc465.jpg':93,
    '06f5fb5111407012c784c9b299befba7.jpg':94,
    '81681c93e0c4eda2444ebf3584edf0d9.jpg':95,
    'b20e0f37595cfe886e51979f19097c5c.jpg':95,
    'cc2d9e5b8ea465c222a1c46f9a3238e4.jpg':96,
    '412956717ee598d2b3f8eb7ca4e382a8.jpg':97,
    '8d730517b1a0c2ade1a008ab94ed62f5.jpg':98,
    '18cbb678f2b0ac9d451659fe6afefa77.jpg':99,
    '2f17bc4fdc96d94317b140ef5c85069c.jpg':100,
    'ecbed71060472f69c17b1fd84e825ea0.jpg':101,
    'be060dfe3d2a20a1a7b7d1f8b96a6f4e.jpg':102,
    '541fe973f044eae53d57ec744c7d52ac.jpg':103,
    'ee33588b40135defe557928a4e4151f4.jpg':104,
    '3426bceae378ec4e7a5744739370591e.jpg':105,
    '5269447a5be1ba6c04589f9338a06129.jpg':126,
    'a9e699fdc58d37f0b9ce8ab66bcdb0e7.jpg':127,
    '937952e1ace56a3aaf16f19d8ea878ad.jpg':128,
}

s = OCR.read_text(encoding='utf-8', errors='replace')
parts = re.split(r'≦\s*([^≧]+?)\s*≧', s)
byname = {parts[i].strip(): parts[i+1].strip() for i in range(1,len(parts),2)}

def clean_text(text):
    out=[]; removed=[]
    for line in text.splitlines():
        raw = line.strip().replace('\x00','')
        if (re.search(r'HONOR\s*80|160MP\s*Matrix\s*Camera|MatrixC|\bCamera\b|^amera$', raw, re.I)
            or re.fullmatch(r'2026[/-]10[/-]13\s*\d{0,2}:?\d{0,2}:?\d{0,2}', raw)
            or re.fullmatch(r'2026[/-]10[/-]13\s*\d*', raw)):
            removed.append(raw); continue
        out.append(line)
    return '\n'.join(out).strip(), removed

cleaned={}; removed=[]
for n,t in byname.items():
    cleaned[n], rm = clean_text(t)
    removed.extend((n,x) for x in rm)

# OCR-visible printed page number for IMG pages, used for audit only. Their time-stamped names
# are already in the photographed page order; the anchors below confirm that order.
def img_page_hint(text):
    # Only accept a number when it is part of the running header.  The OCR body
    # contains many ordinary numbers (for example "8、" and "24 小时"); those
    # must never be presented as the printed page number.
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    candidates = lines[:8] + lines[-8:]
    for q in candidates:
        if len(q) > 60:
            continue
        patterns = (
            # 供水安全生产规程·56· / 第一篇生产调度规程·1·
            r'(?:规程|生产规程)\s*[·。]\s*(\d{1,3})\s*[·。]?',
            # ·56·供水安全生产规程 / 56·供水安全生产规程
            r'^[·。]?\s*(\d{1,3})\s*[·。]\s*(?:供水|生产|提水|规程)',
            # Header OCR occasionally drops the title but keeps the two dots.
            r'^[·。]\s*(\d{1,3})\s*[·。]\s*$',
        )
        for pat in patterns:
            m=re.search(pat,q)
            if m:
                v=int(m.group(1))
                if 1 <= v <= 400 and v not in (80,160,380):
                    return v
    return None

hash_names=sorted([n for n in byname if n in HASH_PAGE], key=lambda n:(HASH_PAGE[n],n))
img_names=sorted([n for n in byname if n.startswith('IMG_')], key=lambda n:n.lower())

pdfmetrics.registerFont(TTFont('SimHei','C:/Windows/Fonts/simhei.ttf'))
styles=getSampleStyleSheet()
title=ParagraphStyle('title',parent=styles['Title'],fontName='SimHei',fontSize=17,leading=22,alignment=TA_CENTER,spaceAfter=10)
sub=ParagraphStyle('sub',parent=styles['Heading2'],fontName='SimHei',fontSize=10.2,leading=14,spaceBefore=2,spaceAfter=5)
body=ParagraphStyle('body',parent=styles['BodyText'],fontName='SimHei',fontSize=8.9,leading=12.4,spaceAfter=2)
small=ParagraphStyle('small',parent=body,fontSize=7.8,leading=10.5,textColor='#555555')

def make_pdf(path, title_text, selected, desc):
    doc=SimpleDocTemplate(str(path), pagesize=A4, rightMargin=15*mm,leftMargin=15*mm,topMargin=13*mm,bottomMargin=14*mm,title=title_text)
    story=[Paragraph(escape(title_text),title), Paragraph(escape(desc),small), Spacer(1,5)]
    for idx, item in enumerate(selected,1):
        if idx>1: story.append(PageBreak())
        name=item['name']; pno=item.get('page')
        ptxt=f'印刷页码：{pno}' if pno is not None else '印刷页码：照片中未清晰识别'
        story.append(Paragraph(f'{escape(ptxt)}｜图片：{escape(name)}',sub))
        lines=[x.strip() for x in cleaned.get(name,'').splitlines() if x.strip()]
        if not lines: lines=['（本页未识别到文字）']
        for line in lines:
            story.append(Paragraph(escape(line),body))
    def footer(c,d):
        c.saveState(); c.setFont('SimHei',7.5); c.setFillColorRGB(.35,.35,.35)
        c.drawCentredString(A4[0]/2,7.5*mm,f'{title_text}  |  OCR PDF页 {d.page}')
        c.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)

hash_items=[{'name':n,'page':HASH_PAGE[n]} for n in hash_names]
img_items=[{'name':n,'page':img_page_hint(byname[n])} for n in img_names]
all_items=[{'name':n,'page':HASH_PAGE[n],'book':'工程资料'} for n in hash_names] + [{'name':n,'page':img_page_hint(byname[n]),'book':'提水泵站规程'} for n in img_names]

make_pdf(OUT/'工程资料_按印刷页码_去水印重排版.pdf','工程资料（按印刷页码·去水印重排版）',hash_items,'按照照片中书页底部印刷页码排序；缺失页码的照片未加入，本资料组共 38 张照片（含同一印刷页的重复照片）。')
make_pdf(OUT/'提水泵站规程_按印刷页码_去水印重排版.pdf','提水泵站规程（按印刷页码·去水印重排版）',img_items,'按照片拍摄顺序重排；该顺序与照片中连续印刷页码相符，并清理相机水印文字。')
# Combined document keeps the two books as separate sections, each in its own page-number order.
combined=[{'name':'__section_engineering__','page':None,'book':'工程资料'}] + all_items[:len(hash_items)] + [{'name':'__section_pump__','page':None,'book':'提水泵站规程'}] + all_items[len(hash_items):]
# section markers are rendered as simple title pages by a wrapper

def make_combined(path):
    doc=SimpleDocTemplate(str(path),pagesize=A4,rightMargin=15*mm,leftMargin=15*mm,topMargin=13*mm,bottomMargin=14*mm,title='二阶段资料（按印刷页码重排版）')
    story=[Paragraph('二阶段资料（按印刷页码·去水印重排版）',title),Paragraph('两本资料分别按各自照片中的印刷页码/连续拍摄顺序整理。',small),Spacer(1,5)]
    current=None; idx=0
    for item in combined:
        if item['name'].startswith('__section_'):
            if idx: story.append(PageBreak())
            section='工程资料' if item['book']=='工程资料' else '提水泵站规程'
            story += [Paragraph(escape(section),title),Paragraph('以下页面已按本书页码顺序排列。',small)]
            current=item['book']; idx+=1; continue
        story.append(PageBreak()); idx+=1
        ptxt=f'印刷页码：{item["page"]}' if item.get('page') is not None else '印刷页码：照片中未清晰识别'
        story.append(Paragraph(f'{escape(ptxt)}｜图片：{escape(item["name"])}',sub))
        lines=[x.strip() for x in cleaned.get(item['name'],'').splitlines() if x.strip()] or ['（本页未识别到文字）']
        for line in lines: story.append(Paragraph(escape(line),body))
    def footer(c,d):
        c.saveState(); c.setFont('SimHei',7.5); c.setFillColorRGB(.35,.35,.35); c.drawCentredString(A4[0]/2,7.5*mm,f'二阶段资料  |  OCR PDF页 {d.page}'); c.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
make_combined(OUT/'二阶段资料_按印刷页码_去水印重排版.pdf')

with (OUT/'二阶段_印刷页码映射清单.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f); w.writerow(['资料分组','排序序号','印刷页码','图片文件名','排序依据','备注'])
    for i,it in enumerate(hash_items,1):
        note='同页重复照片' if sum(1 for x in hash_items if x['page']==it['page'])>1 else ''
        w.writerow(['工程资料',i,it['page'],it['name'],'照片页码核对',note])
    for i,it in enumerate(img_items,1):
        w.writerow(['提水泵站规程',i,it['page'] or '',it['name'],'拍摄时间顺序（与连续印刷页码核对）','OCR未清晰读出页码' if not it['page'] else ''])
with (OUT/'二阶段_已删除水印清单_重排版.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f); w.writerow(['图片文件名','删除的水印文字']); w.writerows(removed)
print('hash',len(hash_items),'img',len(img_items),'removed',len(removed),'out',OUT)
print('hash order',[(x['page'],x['name'][:8]) for x in hash_items])
