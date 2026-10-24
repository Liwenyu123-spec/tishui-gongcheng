from PIL import Image
for n in ['9cbff1c753aeca2a27421a04d7a8fdbc.jpg','a1a2a852f47c3e145aac0f71838da31d.jpg']:
 p='H:/二阶段/图片/'+n; im=Image.open(p)
 if im.width>im.height: im=im.rotate(90,expand=True)
 w,h=im.size
 # make bottom right/mid all
 for label,box in [('br',(int(w*.65),int(h*.72),w,int(h*.98))),('bottom',(0,int(h*.72),w,int(h*.98)))]:
  im.crop(box).resize((1200,500)).save(f'H:/Python工程/提水工程项目/tmp/{n[:8]}_{label}.png')
