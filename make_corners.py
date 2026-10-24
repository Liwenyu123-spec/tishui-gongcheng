from PIL import Image,ImageDraw,ImageFont
from pathlib import Path
src=Path('H:/二阶段/图片'); fs=[p for p in sorted(src.glob('*.jpg'),key=lambda p:p.name.lower()) if len(p.stem)==32]
for region,name in [((0,.78,.35,1),'left'),((.65,.78,1,1),'right')]:
 thumbs=[]; font=ImageFont.load_default()
 for p in fs:
  im=Image.open(p).convert('RGB'); w,h=im.size; crop=im.crop((int(w*region[0]),int(h*region[1]),int(w*region[2]),int(h*region[3]))); crop.thumbnail((260,180)); c=Image.new('RGB',(280,220),'white'); c.paste(crop,((280-crop.width)//2,5)); ImageDraw.Draw(c).text((5,190),p.name[:8],fill='black',font=font); thumbs.append(c)
 cols=4; rows=(len(thumbs)+3)//4; s=Image.new('RGB',(cols*280,rows*220),'#ddd')
 for i,t in enumerate(thumbs): s.paste(t,((i%cols)*280,(i//cols)*220))
 s.save(f'H:/Python工程/提水工程项目/tmp/hash_{name}_corner.jpg',quality=90)
