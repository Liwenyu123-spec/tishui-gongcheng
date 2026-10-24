from PIL import Image,ImageDraw,ImageFont
from pathlib import Path
src=Path(r'H:/二阶段/图片'); fs=[p for p in sorted(src.glob('*.jpg'),key=lambda p:p.name.lower()) if len(p.stem)==32]
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',18)
thumbs=[]
for p in fs:
 im=Image.open(p).convert('RGB')
 if im.width>im.height: im=im.rotate(90,expand=True)
 im.thumbnail((300,400))
 c=Image.new('RGB',(320,440),'white'); c.paste(im,((320-im.width)//2,5)); ImageDraw.Draw(c).text((5,415),p.name[:8],fill='black',font=font); thumbs.append(c)
cols=4; rows=(len(thumbs)+cols-1)//cols; sheet=Image.new('RGB',(cols*320,rows*440),'#ddd')
for i,t in enumerate(thumbs): sheet.paste(t,((i%cols)*320,(i//cols)*440))
sheet.save(r'H:/Python工程/提水工程项目/tmp/hash_upright_full.jpg',quality=90)
