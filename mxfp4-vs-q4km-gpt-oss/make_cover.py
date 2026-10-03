from PIL import Image, ImageDraw, ImageFont
W,H=2752,1536
BG=(15,19,38); WHITE=(240,242,255); MUTE=(120,128,170); CY=(76,201,240); OR=(247,167,36); CYD=(40,120,150)
img=Image.new("RGB",(W,H),BG); d=ImageDraw.Draw(img)
M="/System/Library/Fonts/Menlo.ttc"
def f(sz,bold=False): return ImageFont.truetype(M,sz,index=1 if bold else 0)
x0=128
d.text((x0,92),"H A R D   N U M B E R S",font=f(40),fill=MUTE)
d.text((x0,170),"MXFP4 vs Q4_K_M",font=f(150,True),fill=WHITE)
d.text((x0,340),"on gpt-oss-20B",font=f(110,True),fill=WHITE)
d.text((x0,540),"93%",font=f(420,True),fill=CY)
d.text((1230,640),"of the \"Q4_K_M\" file's bytes",font=f(64),fill=MUTE)
d.text((1230,725),"are identical to the MXFP4 file",font=f(64),fill=MUTE)
for i,t in enumerate(["398 / 459 tensors identical","gpt-oss-20B · llama.cpp 0.5.0","Apple M2 24 GB"]):
    tw=d.textlength(t,font=f(44)); d.text((W-128-tw,92+i*62),t,font=f(44),fill=MUTE)
def bar(y,label,size,parts):
    d.text((x0,y),label,font=f(46),fill=WHITE)
    tw=d.textlength(size,font=f(46)); d.text((W-128-tw,y),size,font=f(46),fill=MUTE)
    bw=W-2*x0; x=x0; by=y+70
    for frac,col in parts:
        w=int(bw*frac); d.rectangle([x,by,x+w,by+110],fill=col); x+=w
bar(1000,"\"Q4_K_M\" file","10.86 GiB",[(0.871,CY),(0.061,CYD),(0.069,OR)])
bar(1230,"MXFP4 file","11.27 GiB",[(0.839,CY),(0.059,CYD),(0.102,OR)])
lx=x0; ly=1420
for col,t in [(CY,"expert weights, identical"),(CYD,"other identical tensors"),(OR,"differ (embeddings + attention)")]:
    d.rectangle([lx,ly+6,lx+34,ly+40],fill=col); d.text((lx+50,ly),t,font=f(36),fill=MUTE); lx+=int(d.textlength(t,font=f(36)))+130
img.save("mxfp4-vs-q4km-cover.png")  # run from this folder
