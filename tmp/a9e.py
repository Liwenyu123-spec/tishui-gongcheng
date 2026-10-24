from PIL import Image
n='a9e699fdc58d37f0b9ce8ab66bcdb0e7.jpg'; im=Image.open('H:/二阶段/图片/'+n); w,h=im.size; im.crop((0,int(h*.80),w,h)).resize((1400,500)).save('H:/Python工程/提水工程项目/tmp/a9e_bottom.png')
