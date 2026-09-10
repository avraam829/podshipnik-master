from PIL import Image, ImageDraw
from pathlib import Path
import math
root = Path(__file__).resolve().parents[1] / 'static'
image = Image.new('RGB', (512,512), '#075b9b')
draw = ImageDraw.Draw(image)
draw.ellipse((40,40,472,472), outline='white', width=32)
draw.ellipse((160,160,352,352), outline='white', width=32)
for i in range(8):
    angle=i*math.pi/4
    x,y=256+152*math.cos(angle),256+152*math.sin(angle)
    draw.ellipse((x-30,y-30,x+30,y+30), fill='white')
image.save(root/'icon-512.png')
image.resize((180,180),Image.Resampling.LANCZOS).save(root/'apple-touch-icon.png')
image.save(root/'favicon.ico',sizes=[(16,16),(32,32),(48,48)])
