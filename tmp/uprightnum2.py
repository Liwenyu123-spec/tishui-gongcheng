from PIL import Image,ImageDraw,ImageFont
from pathlib import Path
src=Path(r'H:/二阶段/图片'); fs=[p for p in sorted(src.glob('*.jpg'),key=lambda p:p.name.lower()) if len(p.stem)==32]
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',24)
thumbs=[]
for p in fs:
 im=Image.open(p).convert('RGB')
 if im.width>im.height: im=im.rotate(90,expand=True)
 w,h=im.size
 crop=im.crop((0,int(h*.78),w,int(h*.98)))
 crop.thumbnail((600,300))
 c=Image.new('RGB',(640,350),'white'); c.paste(crop,((640-crop.width)//2,5)); ImageDraw.Draw(c).text((5,320),p.name[:8],fill='black',font=font); thumbs.append(c)
cols=3; rows=(len(thumbs)+cols-1)//cols; sheet=Image.new('RGB',(cols*640,rows*350),'#ddd')
for i,t in enumerate(thumbs): sheet.paste(t,((i%cols)*640,(i//cols)*350))
sheet.save(r'H:/Python工程/提水工程项目/tmp/hash_upright_num2.jpg',quality=95)
