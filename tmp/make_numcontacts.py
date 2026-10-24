from PIL import Image,ImageDraw,ImageFont
from pathlib import Path
src=Path(r'H:/二阶段/图片'); fs=[p for p in sorted(src.glob('*.jpg'),key=lambda p:p.name.lower()) if len(p.stem)==32]
for region,name in [((0,.62,.35,.88),'numleft'),((.25,.62,.75,.88),'nummid'),((.65,.62,1,.88),'numright')]:
 thumbs=[]; font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',24)
 for p in fs:
  im=Image.open(p).convert('RGB'); w,h=im.size; crop=im.crop((int(w*region[0]),int(h*region[1]),int(w*region[2]),int(h*region[3]))); crop.thumbnail((500,300)); c=Image.new('RGB',(540,350),'white'); c.paste(crop,((540-crop.width)//2,5)); ImageDraw.Draw(c).text((5,315),p.name[:8],fill='black',font=font); thumbs.append(c)
 cols=3; rows=(len(thumbs)+cols-1)//cols; sheet=Image.new('RGB',(cols*540,rows*350),'#ddd')
 for i,t in enumerate(thumbs): sheet.paste(t,((i%cols)*540,(i//cols)*350))
 sheet.save(f'H:/Python工程/提水工程项目/tmp/hash_{name}_large.jpg',quality=92)
