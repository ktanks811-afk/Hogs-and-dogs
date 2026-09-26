# Build the Quarter Horse master (the one body every Quarter Horse coat is painted onto) from qh_reference.png.
# Output channels (PNG, 1024x683), read by the horse coat renderer in index.html (HORSE_MASTERS.quarter):
#   m1 = shading (0..255 = 0..2x lighting) | black-point amount on legs/ears | mane-tail-forelock hair amount
#   m2 = region id x20 | leg id x50 (1 far hind, 2 near hind, 3 near front, 4 far front) | height up the leg (0 coronet .. 255 = 2x knee)
#   m3 = alpha | halter (128 leather, 255 brass) | distance below the topline (px/2)
# Regions: 1 body 2 head 3 muzzle 4 ear 5 eye 6 nostril 7 hoof 8 mane 9 tail 11 lower leg 12 forelock
# Run:  python3 tools/horse/build_qh_master.py [--preview out.png]   (pillow, numpy, scipy)
import os,sys,io,base64,json
from PIL import Image,ImageDraw
import numpy as np
from scipy import ndimage as ndi
HERE=os.path.dirname(os.path.abspath(__file__))
W,H=1536,1024
src=np.array(Image.open(os.path.join(HERE,'qh_reference.png')).convert('RGB')).astype(np.float32)
R_,G_,B_=src[...,0],src[...,1],src[...,2];L=src.mean(2);mx=src.max(2);mn=src.min(2);sat=(mx-mn)/np.maximum(mx,1);val=mx/255
yy,xx=np.mgrid[0:H,0:W]
def poly(pts):
    im=Image.new('L',(W,H),0);ImageDraw.Draw(im).polygon(pts,fill=255);return np.array(im)>0
def ell(cx,cy,rx,ry):return ((xx-cx)/rx)**2+((yy-cy)/ry)**2<=1
def ss(a,b,x):t=np.clip((x-a)/(b-a),0,1);return t*t*(3-2*t)
def lines(segs,width):
    im=Image.new('L',(W,H),0);d=ImageDraw.Draw(im)
    for s in segs:d.line(s,fill=255,width=width,joint='curve')
    return np.array(im)>0

# ---- alpha: hair and hide carry fine texture; the dark backdrop and its glow are smooth ----
det=ndi.gaussian_filter(np.abs(L-ndi.gaussian_filter(L,2.5)),2)
tex=(det>1.0)&(L>6)
tex=ndi.binary_opening(tex,iterations=2)
lab,n=ndi.label(tex);sizes=ndi.sum(tex,lab,range(1,n+1));tex=np.isin(lab,1+np.nonzero(sizes>6000)[0])
core=ndi.binary_fill_holes(ndi.binary_closing(tex,iterations=6))
core=ndi.binary_opening(core,iterations=3)
core=ndi.gaussian_filter(core.astype(np.float32),2.5)>.5
# the tail thins into loose hair: keep it soft instead of a hard cut
tailzone=poly([(390,285),(300,300),(230,420),(170,620),(120,860),(150,960),(260,990),(330,960),(318,640),(345,420),(385,330)])
soft=np.clip((det-.6)/1.6,0,1)*ss(4,18,L)
alpha=np.where(core,1.0,0.0)
alpha=np.maximum(alpha,np.where(tailzone,ndi.gaussian_filter(soft,1.2),0))
alpha=ndi.gaussian_filter(alpha,.8);alpha[core&~tailzone]=np.maximum(alpha[core&~tailzone],.98)
A=alpha>.35

# ---- regions ----
reg=np.ones((H,W),np.uint8)
head=poly([(1195,55),(1245,20),(1280,60),(1305,15),(1345,20),(1350,80),(1392,160),(1425,240),(1440,300),(1420,345),(1360,348),(1320,320),(1290,300),(1245,270),(1200,210),(1185,140)])
reg[head&A]=2
muzzle=poly([(1342,268),(1380,250),(1420,262),(1440,300),(1425,345),(1375,350),(1330,322)])&A&(sat<.62)
muzzle=ndi.binary_fill_holes(ndi.binary_closing(muzzle,iterations=3))&A
reg[muzzle]=3
ears=(poly([(1228,90),(1238,40),(1255,8),(1275,30),(1280,75),(1262,95)])|poly([(1300,80),(1310,35),(1332,8),(1345,35),(1342,80),(1322,92)]))&A
reg[ears]=4
eye=ell(1290,155,15,10);reg[eye&A]=5
nostril=ell(1397,293,22,19)&(L<70);nostril=ndi.binary_fill_holes(ndi.binary_closing(nostril,iterations=2));reg[nostril&A]=6
# legs: each leg its own strip; coronet (top of the hoof) and knee/hock heights set the sock scale
LEGS={1:dict(poly=[(305,620),(405,620),(418,760),(398,950),(425,1015),(305,1015),(316,950),(308,800)],cor=955,knee=705),
      2:dict(poly=[(412,640),(565,610),(520,720),(503,840),(540,930),(605,1012),(470,1015),(455,930),(424,840),(412,740)],cor=950,knee=740),
      3:dict(poly=[(858,630),(992,630),(986,760),(966,900),(990,1015),(868,1015),(878,940),(868,800)],cor=962,knee=770),
      4:dict(poly=[(992,630),(1112,630),(1094,760),(1082,900),(1108,1012),(996,1015),(1004,940),(994,800)],cor=956,knee=745)}
legid=np.zeros((H,W),np.uint8);legh=np.zeros((H,W),np.float32)
for k,v in LEGS.items():
    m=poly(v['poly'])&A&(legid==0);legid[m]=k;legh[m]=np.clip((v['cor']-yy[m])/(v['cor']-v['knee']),0,2)
    hoof=m&(yy>=v['cor']);reg[hoof]=7
blackish=ss(.48,.22,sat)*ss(.42,.12,val)       # low saturation and dark: black hair and points
pts=np.zeros((H,W),np.float32)
legs=legid>0
pts[legs]=blackish[legs]
pts=np.where(legs,np.maximum(pts,ss(0,-.15,-(legh-.95))*.0),pts)
pts=ndi.gaussian_filter(pts,1.2)*legs
lowleg=legs&(legh<1.25)&(reg!=7)
reg[lowleg]=11
# ear tips go dark on bay-type coats
eartip=ears&(yy<45);pts=np.maximum(pts,np.where(eartip,blackish,0))
# mane (crest to withers), forelock, tail
manez=poly([(790,300),(860,255),(950,190),(1040,125),(1120,80),(1190,50),(1240,55),(1225,95),(1190,120),(1120,170),(1060,215),(990,265),(900,320),(820,330)])
forelock=poly([(1262,60),(1300,62),(1330,100),(1310,112),(1280,100),(1258,85)])
tail=tailzone&~legs
hair=np.zeros((H,W),np.float32)
for z in(manez,forelock,tail):hair=np.maximum(hair,np.where(z,blackish,0))
hair=ndi.gaussian_filter(hair,1)
reg[(manez&(hair>.35))&A]=8;reg[(forelock&(hair>.35))&A]=12;reg[tail&(hair>.2)&(alpha>.05)]=9
hair=np.where(reg==9,np.maximum(hair,.85),hair)
# halter: hand-traced straps and brass
straps=lines([[(1230,62),(1222,95),(1214,128)],[(1218,152),(1221,170)],[(1228,186),(1248,204),(1268,222),(1290,240)],[(1318,240),(1345,226),(1372,214),(1398,208)],[(1301,262),(1299,282),(1301,298)]],13)
brass=lines([[(1204,126),(1227,126),(1227,152),(1204,152),(1204,126)]],5)|(ell(1223,177,11,11)&~ell(1223,177,6,6))|lines([[(1292,232),(1318,236),(1314,262),(1290,258),(1292,232)]],6)|ell(1301,303,7,6)
halter=np.zeros((H,W),np.uint8);halter[straps&A]=128;halter[brass&A]=255
# ---- shading: each surface lit relative to its own typical brightness, so a new colour keeps the photo's light ----
Lb=ndi.gaussian_filter(L,1)
bayref=np.median(Lb[(reg==1)&(blackish<.2)&A]);blkref=np.median(Lb[((pts>.6)|(hair>.6))&A]);hoofref=np.median(Lb[reg==7])
dark=np.clip(np.maximum(pts,hair),0,1)
ref=bayref*(1-dark)+blkref*dark
ref=np.where(reg==7,hoofref,ref)
shade=Lb/np.maximum(ref,1)
# the reference's own white star is painted over: its lighting is filled from the coat around it
star=poly([(1318,100),(1350,100),(1362,150),(1330,150)])&(sat<.2)&(L>150)
star=ndi.binary_dilation(star,iterations=3)
if star.any():
    fill=ndi.gaussian_filter(np.where(star,0,shade),6)/np.maximum(ndi.gaussian_filter((~star).astype(np.float32),6),1e-3)
    shade=np.where(star,fill*.95,shade)
shade=np.clip(shade,0,2)
# distance below the topline (dun dorsal stripe, sooty shading on the top)
top=np.full(W,H);colA=A&(reg!=8)&(reg!=12)
for x in range(W):
    c=np.nonzero(colA[:,x])[0]
    if len(c):top[x]=c[0]
tdist=np.clip((yy-top[None,:])/2,0,255)
# ---- write the maps at 1024x683 ----
OW,OH=1024,683
def ch(a):return np.clip(a,0,255).astype(np.uint8)
m1=np.dstack([ch(shade*127.5),ch(pts*255),ch(hair*255)])
m2=np.dstack([ch(reg.astype(np.float32)*20),ch(legid.astype(np.float32)*50),ch(legh*127.5)])
m3=np.dstack([ch(alpha*255),halter,ch(tdist)])
def rs(a,nearest):return Image.fromarray(a).resize((OW,OH),Image.NEAREST if nearest else Image.LANCZOS)
maps={'m1':rs(m1,False),'m2':rs(m2,True),'m3':rs(m3,False)}
out={}
for k,im in maps.items():
    b=io.BytesIO();im.save(b,'PNG',optimize=True);out[k]='data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()
sc=OW/W
meta={'w':OW,'h':OH,'face':{'a':[1328*sc,108*sc],'b':[1404*sc,276*sc]},'legs':{k:{'cor':v['cor']*sc,'knee':v['knee']*sc} for k,v in LEGS.items()}}
json.dump({'meta':meta,'maps':out},open(os.path.join(HERE,'qh_master.json'),'w'))
print('bay ref',bayref,'black ref',blkref,'hoof',hoofref,'sizes',{k:len(v) for k,v in out.items()})
if '--preview' in sys.argv:
    p=sys.argv[sys.argv.index('--preview')+1]
    cols=np.array([[0,0,0],[160,120,90],[200,90,60],[230,170,150],[120,60,160],[40,200,240],[240,40,200],[200,200,200],[40,40,40],[80,80,80],[0,0,0],[90,140,60],[20,90,40]],np.uint8)
    pr=cols[np.minimum(reg,12)];pr[halter==128]=[160,40,40];pr[halter==255]=[255,215,0];pr[legid>0]=pr[legid>0]*.6+np.array([[0,0,0],[255,0,0],[0,255,0],[0,0,255],[255,255,0]])[legid[legid>0]]*.4
    pr=(pr*alpha[...,None]).astype(np.uint8)
    Image.fromarray(np.hstack([pr,np.dstack([ch(shade*110)]*3)])).resize((1536,512)).save(p)
