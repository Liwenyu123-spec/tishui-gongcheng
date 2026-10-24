from PIL import Image
for n in ['9cbff1c753aeca2a27421a04d7a8fdbc.jpg','a1a2a852f47c3e145aac0f71838da31d.jpg']:
 im=Image.open('H:/二阶段/图片/'+n).convert('RGB')
 for angle in [90,270]:
  x=im.rotate(angle,expand=True); w,h=x.size
  x.crop((0,int(h*.72),w,int(h*.98))).resize((1200,500)).save(f'H:/Python工程/提水工程项目/tmp/{n[:8]}_{angle}.png')
