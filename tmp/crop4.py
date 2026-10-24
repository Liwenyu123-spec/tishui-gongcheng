from PIL import Image
for n in ['a671050810ce24247662e0a79e7028e8.jpg','937952e1ace56a3aaf16f19d8ea878ad.jpg']:
 im=Image.open('H:/二阶段/图片/'+n)
 if im.width>im.height: im=im.rotate(270,expand=True)
 w,h=im.size
 im.crop((0,int(h*.82),w,h)).resize((1400,500)).save(f'H:/Python工程/提水工程项目/tmp/{n[:8]}_bottom.png')
