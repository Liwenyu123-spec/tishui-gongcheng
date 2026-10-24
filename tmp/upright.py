from PIL import Image,ImageDraw,ImageFont
from pathlib import Path
src=Path(r'H:/二阶段/图片'); fs=[p for p in sorted(src.glob('*.jpg'),key=lambda p:p.name.lower()) if len(p.stem)==32]
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',20)
thumbs=[]
for p in fs:
 im=Image.open(p).convert('RGB')
 if im.width>im.height: im=im.rotate(90,expand=True)
 w,h=im.size
 crop=im.crop((0,int(h*.72),w,h))
 crop.thumbnail((450,300))
 c=Image.new('RGB',(480,345),'white'); c.paste(crop,((480-crop.width)//2,5)); ImageDraw.Draw(c).text((5,320),p.name[:8],fill='black',font=font); thumbs.append(c)
cols=3; rows=(len(thumbs)+2)//3; sheet=Image.new('RGB',(cols*480,rows*345),'#ddd')
for i,t in enumerate(thumbs): sheet.paste(t,((i%cols)*480,(i//cols)*345))
sheet.save(r'H:/Python工程/提水工程项目/tmp/hash_upright_bottom.jpg',quality=90)
