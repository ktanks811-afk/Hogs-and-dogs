# Build the hog master (the one body every hog's coat is painted onto) from hog_reference.png.
# The reference has a checkerboard painted in where transparency would be; it is cut away by colour.
# Output channels (PNG, 1024x683), read by the hog renderer in index.html (HOG_MASTERS.wild):
#   m1 = shading (0..255 = 0..2x lighting) | hair detail (128 = flat) | tan-ness of the reference coat (its patch layout)
#   m2 = region id x20 | reach along the part (tusk base->tip, ear base->tip, tail root->tip, leg hoof->knee) | leg id x50
#   m3 = alpha | 0 | distance below the topline (px/2)
# Regions: 1 body 2 head 3 snout 4 ear 5 eye 6 tusk 7 hoof 8 bristle crest 9 tail 11 lower leg
# Run:  python3 tools/hog/build_hog_master.py [--preview out.png]   (pillow, numpy, scipy); then tools/assets/extract_masters.py
import os,sys,io,base64,json
from PIL import Image,ImageDraw
import numpy as np
from scipy import ndimage as ndi
HERE=os.path.dirname(os.path.abspath(__file__))
W,H=1536,1024
src=np.array(Image.open(os.path.join(HERE,'hog_reference.png')).convert('RGB')).astype(np.float32)
R_,G_,B_=src[...,0],src[...,1],src[...,2];L=src.mean(2);mx=src.max(2);mn=src.min(2);sat=(mx-mn)/np.maximum(mx,1);warm=R_-B_
yy,xx=np.mgrid[0:H,0:W]
def poly(pts):
    im=Image.new('L',(W,H),0);ImageDraw.Draw(im).polygon(pts,fill=255);return np.array(im)>0
def ell(cx,cy,rx,ry):return ((xx-cx)/rx)**2+((yy-cy)/ry)**2<=1
def ss(a,b,x):t=np.clip((x-a)/(b-a),0,1);return t*t*(3-2*t)
def reach(mask,a,b):
    ax,ay=a;bx,by=b;dx,dy=bx-ax,by-ay;t=((xx-ax)*dx+(yy-ay)*dy)/(dx*dx+dy*dy);return np.where(mask,np.clip(t,0,1),0)
# ---- alpha: the painted checkerboard is bright, grey and neutral; the hog is dark, brown or warm ----
bgl=(sat<.11)&(L>178)&(warm<9)
core=~bgl
core=ndi.binary_opening(core,iterations=2)
lab,n=ndi.label(core);sizes=ndi.sum(core,lab,range(1,n+1));core=np.isin(lab,1+np.argmax(sizes))
core=ndi.binary_closing(core,iterations=3)
holes=ndi.binary_fill_holes(core)&~core;hl,hn=ndi.label(holes);hs=ndi.sum(holes,hl,range(1,hn+1));core=core|np.isin(hl,1+np.nonzero(hs<500)[0])
core=ndi.binary_opening(core,iterations=1)
crestP=poly([(640,160),(720,95),(820,40),(900,12),(1000,8),(1100,20),(1200,62),(1265,105),(1305,160),(1220,172),(1100,152),(1000,142),(900,152),(800,172),(700,192)])
tailP=poly([(176,378),(130,360),(88,362),(46,386),(14,420),(4,472),(24,534),(56,588),(96,596),(104,520),(98,452),(122,424),(162,446),(186,424)])
belly=poly([(300,560),(1250,560),(1250,780),(300,780)])
beard=poly([(1140,540),(1420,540),(1420,690),(1140,690)])
hairy=crestP|tailP|belly|beard
soft=np.clip((200-L)/75,0,1)*(warm<60)
alpha=np.where(core,1.0,0.0)
alpha=np.maximum(alpha,np.where(hairy&~core,ndi.gaussian_filter(soft,.8),0))
alpha=ndi.gaussian_filter(alpha,.7);alpha[core]=np.maximum(alpha[core],.97)
A=alpha>.35
# ---- regions ----
reg=np.ones((H,W),np.uint8);rch=np.zeros((H,W),np.float32);legid=np.zeros((H,W),np.uint8)
head=poly([(1080,118),(1200,128),(1330,160),(1396,148),(1382,262),(1402,380),(1462,450),(1514,540),(1514,622),(1472,652),(1380,652),(1300,664),(1200,652),(1150,602),(1120,482),(1090,352),(1068,222)])
reg[head&A]=2
snout=poly([(1378,468),(1440,478),(1492,518),(1514,560),(1508,612),(1472,644),(1420,644),(1390,602),(1368,540)])&A&~(warm>45)&(L>20)
snout=ndi.binary_fill_holes(ndi.binary_closing(snout,iterations=3))&A;reg[snout]=3
earN=poly([(1072,124),(1120,118),(1182,148),(1202,200),(1192,270),(1150,292),(1108,272),(1084,222),(1066,170)])&A
earF=poly([(1318,202),(1350,168),(1382,142),(1398,148),(1392,212),(1372,266),(1334,272)])&A
reg[earN|earF]=4;rch+=reach(earN,(1170,272),(1082,126))+reach(earF,(1350,266),(1392,150))
eye=ell(1241,347,16,10);reg[eye&A]=5
ivory=(L>105)&(warm>12)
tuskN=poly([(1260,416),(1286,420),(1312,500),(1324,560),(1302,580),(1280,540),(1264,470)])&A&ivory
tuskF=poly([(1486,428),(1508,430),(1524,480),(1522,532),(1500,544),(1490,500)])&A&ivory
tuskN=ndi.binary_closing(tuskN,iterations=2)&A;tuskF=ndi.binary_closing(tuskF,iterations=2)&A
reg[tuskN|tuskF]=6;rch+=reach(tuskN,(1306,568),(1268,424))+reach(tuskF,(1502,538),(1500,436))
tail=tailP&(alpha>.05);reg[tail]=9;rch+=reach(tail,(176,420),(44,576))
crest=crestP&A&~head;reg[crest]=8
LEGS={1:dict(poly=[(470,760),(580,760),(612,915),(470,915)],hoof=[(482,905),(612,912),(614,972),(492,970)],top=912,knee=760),
      2:dict(poly=[(88,760),(236,760),(236,932),(82,932)],hoof=[(80,928),(218,924),(222,988),(82,988)],top=928,knee=760),
      3:dict(poly=[(806,800),(966,800),(1000,945),(826,945)],hoof=[(836,940),(1002,944),(1004,1012),(842,1012)],top=944,knee=790),
      4:dict(poly=[(1050,790),(1206,790),(1270,925),(1086,925)],hoof=[(1096,918),(1288,928),(1288,992),(1100,992)],top=924,knee=780)}
for k,v in LEGS.items():
    lm=poly(v['poly'])&A&(reg==1);hm=poly(v['hoof'])&A&((reg==1)|(reg==11))
    reg[lm]=11;reg[hm]=7;legid[lm|hm]=k
    rch=np.where(lm,np.clip((v['top']-yy)/(v['top']-v['knee']),0,1),rch)
# ---- shading: light relative to the reference's own two hair tones (tan patches, black hair) ----
Lb=ndi.gaussian_filter(L,1)
tan=ss(40,120,ndi.gaussian_filter(L,4))*ss(10,45,ndi.gaussian_filter(warm,4))
tanref=np.median(Lb[(tan>.75)&A&(reg<=2)]);drkref=np.median(Lb[(tan<.15)&A&(reg<=2)])
ref=drkref*(1-tan)+tanref*tan
ref=np.where(reg==6,np.median(Lb[reg==6]),ref);ref=np.where(reg==7,np.median(Lb[reg==7]),ref);ref=np.where(reg==3,np.median(Lb[reg==3]),ref)
shade=Lb/np.maximum(ref,1)
inner=ndi.binary_erosion(A,iterations=3)
fillsh=ndi.gaussian_filter(np.where(inner,shade,0),2.5)/np.maximum(ndi.gaussian_filter(inner.astype(np.float32),2.5),1e-3)
shade=np.where(A&~inner,np.minimum(shade,fillsh*1.05),shade)
shade=np.where((alpha>.02)&~A,np.minimum(shade,1.0),shade)
shade=np.clip(shade,0,2)
detail=np.clip(128+(L-ndi.gaussian_filter(L,1.6))*1.4,0,255)
top=np.full(W,H);colA=A&(reg!=6)
for x in range(W):
    c=np.nonzero(colA[:,x])[0]
    if len(c):top[x]=c[0]
tdist=np.clip((yy-top[None,:])/2,0,255)
# ---- write the maps at 1024x683 ----
OW,OH=1024,683
def ch(a):return np.clip(a,0,255).astype(np.uint8)
m1=np.dstack([ch(shade*127.5),ch(detail),ch(tan*255)])
m2=np.dstack([ch(reg.astype(np.float32)*20),ch(rch*255),ch(legid.astype(np.float32)*50)])
m3=np.dstack([ch(alpha*255),np.zeros((H,W),np.uint8),ch(tdist)])
def rs(a,nearest):return Image.fromarray(a).resize((OW,OH),Image.NEAREST if nearest else Image.LANCZOS)
maps={'m1':rs(m1,False),'m2':rs(m2,True),'m3':rs(m3,False)}
out={}
for k,im in maps.items():
    b=io.BytesIO();im.save(b,'PNG',optimize=True);out[k]='data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()
meta={'w':OW,'h':OH}
json.dump({'meta':meta,'maps':out},open(os.path.join(HERE,'hog_master.json'),'w'))
print('tan ref',tanref,'dark ref',drkref,'sizes',{k:len(v) for k,v in out.items()})
if '--preview' in sys.argv:
    p=sys.argv[sys.argv.index('--preview')+1]
    cols=np.array([[0,0,0],[160,120,90],[200,90,60],[230,170,150],[120,60,160],[40,200,240],[250,240,200],[200,200,200],[40,40,40],[80,80,80],[0,0,0],[90,140,60],[20,90,40]],np.uint8)
    pr=cols[np.minimum(reg,12)];pr=(pr*alpha[...,None]).astype(np.uint8)
    Image.fromarray(np.hstack([pr,np.dstack([ch(shade*110)]*3),np.dstack([ch(tan*255)]*3)])).resize((2304,512)).save(p)
