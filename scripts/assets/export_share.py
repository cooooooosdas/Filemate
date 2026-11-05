from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
root=Path('filemate/web')
image=Image.new('RGB',(1200,630),'#183a7e');draw=ImageDraw.Draw(image)
for x in range(850,1450,55):draw.arc((x-550,-150,x+400,800),70,280,fill='#4063a1',width=2)
logo=Image.open(root/'src/assets/filemate-brand-lockup.png').convert('RGBA');logo.thumbnail((370,110));plate=Image.new('RGBA',(410,138),'#f0f3f8');plate.alpha_composite(logo,((410-logo.width)//2,(138-logo.height)//2));image.paste(plate,(72,64),plate)
font='C:/Windows/Fonts/msyh.ttc';bold='C:/Windows/Fonts/msyhbd.ttc'
draw.text((72,250),'今天，让知识成形。',font=ImageFont.truetype(bold,68),fill='#f4f7fd')
draw.text((76,364),'读资料 · 练代码 · 准备面试',font=ImageFont.truetype(font,35),fill='#bdd3fb')
draw.line((76,480,1124,480),fill='#6d8cc1',width=2)
draw.text((76,522),'FileMate  /  filemate.asia',font=ImageFont.truetype(font,27),fill='#e0e8fb')
out=root/'public/share/filemate-1200x630.png';out.parent.mkdir(parents=True,exist_ok=True)
if out.exists():raise ValueError('refuse overwrite')
image.save(out,optimize=True)
print(out.stat().st_size)
