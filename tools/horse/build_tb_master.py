# Build the Thoroughbred master (the body every Thoroughbred coat is painted onto) from tb_reference.png.
# The reference has a checkerboard painted in where transparency would be; it is cut away by colour, and the three
# white socks (which are checker-coloured too) are traced by hand. Same channels as build_qh_master.py:
# Output channels (PNG, 1024x683), read by the horse coat renderer in index.html (HORSE_MASTERS.thoroughbred):
#   m1 = shading (0..255 = 0..2x lighting) | black-point amount on legs/ears | mane-tail-forelock hair amount
#   m2 = region id x20 | leg id x50 (1 far hind, 2 near hind, 3 near front, 4 far front) | height up the leg (0 coronet .. 255 = 2x knee)
#   m3 = alpha | halter (128 leather, 255 brass) | distance below the topline (px/2)
# Regions: 1 body 2 head 3 muzzle 4 ear 5 eye 6 nostril 7 hoof 8 mane 9 tail 11 lower leg 12 forelock
# Run:  python3 tools/horse/build_tb_master.py [--preview out.png]   (pillow, numpy, scipy); then tools/assets/extract_masters.py
import os,sys,io,base64,json
from PIL import Image,ImageDraw
import numpy as np
from scipy import ndimage as ndi
HERE=os.path.dirname(os.path.abspath(__file__))
W,H=1536,1024
src=np.array(Image.open(os.path.join(HERE,'tb_reference.png')).convert('RGB')).astype(np.float32)
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

# ---- alpha: the painted checkerboard is bright, grey and cool; the horse is dark or warm ----
warm=R_-B_
bgl=(sat<.10)&(L>186)&(warm<7)
socks=poly([(284,846),(336,846),(342,880),(348,930),(360,958),(330,966),(298,966),(282,930),(276,885)])|poly([(498,836),(546,836),(552,875),(566,905),(600,944),(590,958),(556,960),(528,940),(510,900)])|poly([(866,918),(914,922),(938,950),(920,960),(874,960),(860,944)])
core=~bgl
core=ndi.binary_opening(core,iterations=2)
lab,n=ndi.label(core);sizes=ndi.sum(core,lab,range(1,n+1));core=np.isin(lab,1+np.argmax(sizes))
core=core|socks
core=ndi.binary_closing(core,iterations=3)
# only small holes are filled: the gap between the tail and the buttock is real background, fenced in on every side
holes=ndi.binary_fill_holes(core)&~core;hl,hn=ndi.label(holes);hs=ndi.sum(holes,hl,range(1,hn+1));core=core|np.isin(hl,1+np.nonzero(hs<400)[0])
core=ndi.binary_opening(core,iterations=2)
tailzone=poly([(400,258),(330,272),(260,340),(200,440),(150,560),(110,690),(96,800),(120,905),(200,915),(290,868),(330,760),(345,600),(335,420),(380,300)])
dark=ss(200,120,L)*ss(.35,.05,sat*0+np.abs(warm)/80)
hairsoft=np.clip((198-L)/70,0,1)*(sat<.35)
alpha=np.where(core,1.0,0.0)
alpha=np.maximum(alpha,np.where(tailzone&~core,ndi.gaussian_filter(hairsoft,.8),0))
alpha=ndi.gaussian_filter(alpha,.7);alpha[core&~tailzone]=np.maximum(alpha[core&~tailzone],.98)
A=alpha>.35

# ---- regions ----
reg=np.ones((H,W),np.uint8)
head=poly([(1245,58),(1290,38),(1320,8),(1336,30),(1366,12),(1374,60),(1396,110),(1430,190),(1463,258),(1464,300),(1442,326),(1390,327),(1350,302),(1300,266),(1260,242),(1238,200),(1232,120)])
reg[head&A]=2
muzzle=poly([(1372,236),(1430,214),(1463,258),(1464,300),(1442,326),(1390,327),(1362,292)])&A&(sat<.5)
muzzle=ndi.binary_fill_holes(ndi.binary_closing(muzzle,iterations=3))&A
reg[muzzle]=3
ears=(poly([(1288,72),(1298,40),(1330,6),(1338,40),(1326,76)])|poly([(1340,62),(1350,30),(1370,10),(1374,50),(1360,72)]))&A
reg[ears]=4
eye=ell(1328,141,14,9);reg[eye&A]=5
nostril=ell(1430,278,16,18)&(L<80);nostril=ndi.binary_fill_holes(ndi.binary_closing(nostril,iterations=2));reg[nostril&A]=6
# legs: each leg its own strip; coronet (top of the hoof) and knee/hock heights set the sock scale
LEGS={1:dict(poly=[(300,616),(422,616),(382,700),(346,800),(338,860),(348,930),(380,992),(288,1000),(276,900),(284,850),(298,760),(298,700)],cor=959,knee=690),
      2:dict(poly=[(438,600),(562,600),(526,700),(526,780),(546,850),(576,918),(634,975),(622,992),(544,988),(528,932),(503,870),(478,790),(438,722),(433,660)],cor=950,knee=700),
      3:dict(poly=[(888,600),(985,600),(975,700),(950,760),(930,840),(906,900),(952,955),(952,994),(860,994),(848,900),(868,820),(898,740),(904,680)],cor=953,knee=752),
      4:dict(poly=[(986,600),(1072,600),(1062,700),(1056,800),(1066,880),(1082,930),(1142,990),(1132,1008),(1048,1008),(1038,950),(1014,900),(1010,800),(994,700)],cor=960,knee=770)}
legid=np.zeros((H,W),np.uint8);legh=np.zeros((H,W),np.float32)
for k,v in LEGS.items():
    m=poly(v['poly'])&A&(legid==0);legid[m]=k;legh[m]=np.clip((v['cor']-yy[m])/(v['cor']-v['knee']),0,2)
    hoof=m&(yy>=v['cor']);reg[hoof]=7
blackish=ss(.48,.22,sat)*ss(.42,.12,val)       # low saturation and dark: black hair and points
pts=np.zeros((H,W),np.float32)
legs=legid>0
pts[legs]=np.maximum(np.maximum(blackish[legs],np.where(socks[legs],1.0,0)),ss(1.5,1.05,legh[legs]))
pts=np.where(legs,np.maximum(pts,ss(0,-.15,-(legh-.95))*.0),pts)
pts=ndi.gaussian_filter(pts,1.2)*legs
lowleg=legs&(legh<1.25)&(reg!=7)
reg[lowleg]=11
# ear tips go dark on bay-type coats
eartip=ears&(yy<45);pts=np.maximum(pts,np.where(eartip,blackish,0))
# mane (crest to withers), forelock, tail
manez=poly([(812,282),(900,196),(990,140),(1080,88),(1160,52),(1250,36),(1300,55),(1290,92),(1240,92),(1180,122),(1100,172),(1020,232),(950,282),(880,302)])
forelock=poly([(1298,56),(1340,50),(1382,70),(1400,122),(1370,112),(1330,100),(1298,90)])
tail=tailzone&~legs
hair=np.zeros((H,W),np.float32)
for z in(manez,forelock,tail):hair=np.maximum(hair,np.where(z,blackish,0))
hair=ndi.gaussian_filter(hair,1)
reg[(manez&(hair>.35))&A]=8;reg[(forelock&(hair>.35))&A]=12;reg[tail&(hair>.2)&(alpha>.05)]=9
edgeband=A&~ndi.binary_erosion(A,iterations=3)
baycol=(sat>.35)&(warm>25)&(L>30)
tailhair=tailzone&(alpha>.05)&~legs&~baycol
hair=np.where(tailhair|(reg==9),np.maximum(hair,.9),hair)
manehair=manez&A&~baycol&~head
hair=np.where(manehair,1.0,hair)
reg[manehair&((reg==1)|(reg==8))]=8;reg[tailhair]=9
# halter: hand-traced straps and brass
straps=lines([[(1257,60),(1258,110)],[(1260,138),(1262,156)],[(1270,170),(1300,195),(1330,221)],[(1358,214),(1390,200),(1422,193)],[(1262,170),(1250,200),(1255,235),(1290,255),(1325,268)],[(1339,244),(1336,266)]],12)
brass=lines([[(1250,110),(1270,110),(1270,137),(1250,137),(1250,110)]],5)|(ell(1265,163,8,8)&~ell(1265,163,4,4))|lines([[(1332,217),(1358,217),(1358,243),(1332,243),(1332,217)]],5)|(ell(1333,280,8,8)&~ell(1333,280,4,4))
halter=np.zeros((H,W),np.uint8);halter[straps&A]=128;halter[brass&A]=255
# ---- shading: each surface lit relative to its own typical brightness, so a new colour keeps the photo's light ----
Lb=ndi.gaussian_filter(L,1)
bayref=np.median(Lb[(reg==1)&(blackish<.2)&A]);blkref=np.median(Lb[((pts>.6)|(hair>.6))&A&~socks]);hoofref=np.median(Lb[reg==7])
dark=np.clip(np.maximum(pts,hair),0,1)
ref=bayref*(1-dark)+blkref*dark
whiteref=np.median(Lb[socks&A&(L>150)]);wt=np.where(socks&A&(reg!=7),ss(14,55,Lb),0)
ref=np.where(reg==7,hoofref,ref);ref=ref*(1-wt)+whiteref*wt
shade=Lb/np.maximum(ref,1)
# the reference's own white star is painted over: its lighting is filled from the coat around it
star=poly([(1346,92),(1366,92),(1400,150),(1394,162),(1370,142)])&(sat<.25)&(L>140)
star=ndi.binary_dilation(star,iterations=3)
if star.any():
    fill=ndi.gaussian_filter(np.where(star,0,shade),6)/np.maximum(ndi.gaussian_filter((~star).astype(np.float32),6),1e-3)
    shade=np.where(star,fill*.95,shade)
inner=ndi.binary_erosion(A,iterations=3)
fillsh=ndi.gaussian_filter(np.where(inner,shade,0),2.5)/np.maximum(ndi.gaussian_filter(inner.astype(np.float32),2.5),1e-3)
shade=np.where(A&~inner,np.minimum(shade,fillsh*1.05),shade)
soft=(alpha>.02)&~A;shade=np.where(soft,np.minimum(shade,1.0),shade)
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
meta={'w':OW,'h':OH,'face':{'a':[1352*sc,96*sc],'b':[1446*sc,268*sc]},'legs':{k:{'cor':v['cor']*sc,'knee':v['knee']*sc} for k,v in LEGS.items()}}
json.dump({'meta':meta,'maps':out},open(os.path.join(HERE,'tb_master.json'),'w'))
print('bay ref',bayref,'black ref',blkref,'hoof',hoofref,'sizes',{k:len(v) for k,v in out.items()})
if '--preview' in sys.argv:
    p=sys.argv[sys.argv.index('--preview')+1]
    cols=np.array([[0,0,0],[160,120,90],[200,90,60],[230,170,150],[120,60,160],[40,200,240],[240,40,200],[200,200,200],[40,40,40],[80,80,80],[0,0,0],[90,140,60],[20,90,40]],np.uint8)
    pr=cols[np.minimum(reg,12)];pr[halter==128]=[160,40,40];pr[halter==255]=[255,215,0];pr[legid>0]=pr[legid>0]*.6+np.array([[0,0,0],[255,0,0],[0,255,0],[0,0,255],[255,255,0]])[legid[legid>0]]*.4
    pr=(pr*alpha[...,None]).astype(np.uint8)
    Image.fromarray(np.hstack([pr,np.dstack([ch(shade*110)]*3)])).resize((1536,512)).save(p)
