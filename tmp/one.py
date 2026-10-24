from PIL import Image
for n in ['9cbff1c753aeca2a27421a04d7a8fdbc.jpg']:
 im=Image.open('H:/二阶段/图片/'+n).rotate(270,expand=True)
 im.resize((1000,1333)).save('H:/Python工程/提水工程项目/tmp/9cb_upright.png')
