from PIL import Image,ImageOps,ImageDraw,ImageFont
from pathlib import Path
src=Path('H:/二阶段/图片'); out=Path('H:/Python工程/提水工程项目/tmp/hash_bottom_contact.jpg')
files=sorted(src.glob('*.jpg'),key=lambda p:p.name.lower())
files=[p for p in files if len(p.stem)==32]
thumbs=[]; font=ImageFont.load_default()
for p in files:
 im=Image.open(p).convert('RGB'); crop=im.crop((0,int(im.height*0.78),im.width,im.height)); crop.thumbnail((260,180)); canvas=Image.new('RGB',(280,220),'white'); canvas.paste(crop,((280-crop.width)//2,5)); d=ImageDraw.Draw(canvas); d.text((5,190),p.name[:8],fill='black',font=font); thumbs.append(canvas)
cols=4; rows=(len(thumbs)+cols-1)//cols; sheet=Image.new('RGB',(cols*280,rows*220),'#ddd')
for i,t in enumerate(thumbs): sheet.paste(t,((i%cols)*280,(i//cols)*220))
sheet.save(out,quality=90); print(out)
