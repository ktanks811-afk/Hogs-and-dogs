# Build the Dogo Argentino master stack (m1/m2/m3) from the reference painting,
# in the same channel layout the coat engine uses for every other body, and embed
# it in index.html as dogo_stack_v1.
#   m1 = shading | outline ink | white-spread rank
#   m2 = region id x20 (1 body 2 head 3 muzzle 4 ears 5 eye 6 nose 7 paws 8 tail) | saddle field | tan-point field
#   m3 = alpha | facial-mask field | coat length (0 = short)
# Run from anywhere:  python3 tools/dogo/build_dogo_master.py   (needs pillow, numpy, scipy)
import os,re,io,base64
from PIL import Image,ImageDraw
import numpy as np
from scipy import ndimage as ndi
HERE=os.path.dirname(os.path.abspath(__file__));INDEX=os.path.join(HERE,'..','..','index.html')
html=open(INDEX,encoding='utf-8').read()
def body_map(body,n):
    m=re.search(body+r":\{w:1536,h:1024,maps:\{m1:'([^']*)',m2:'([^']*)',m3:'([^']*)'\}\}",html)
    return Image.open(io.BytesIO(base64.b64decode(m.group(n).split(',',1)[1])))
W,H=1536,1024
src=np.array(Image.open(os.path.join(HERE,'dogo_reference.png')).convert('RGB')).astype(np.float32)
L=src.mean(2)
yy,xx=np.mgrid[0:H,0:W]
def poly(pts):
    im=Image.new('L',(W,H),0);ImageDraw.Draw(im).polygon(pts,fill=255);return np.array(im)>0
def ell(cx,cy,rx,ry):return ((xx-cx)/rx)**2+((yy-cy)/ry)**2<=1
def ss(a,b,x):t=np.clip((x-a)/(b-a),0,1);return t*t*(3-2*t)

# ---- alpha: fur is bright, the ink outline and glow are dark ----
fur=L>80
yq,xq=np.mgrid[0:H,0:W]
fur|=(L>45)&(xq>=900)&(xq<=1160)&(yq>=540)&(yq<=770)   # the far hind thigh is painted in deep shadow
fur=ndi.binary_opening(fur,iterations=1)
lab,n=ndi.label(fur);sizes=ndi.sum(fur,lab,range(1,n+1));fur=np.isin(lab,1+np.nonzero(sizes>3000)[0])   # far legs are separate pieces
nose=ell(143,174,30,27)&(ndi.gaussian_filter(L,1.5)<105)
nose=ndi.binary_fill_holes(ndi.binary_closing(nose,iterations=2))
core=ndi.binary_closing(fur|nose,iterations=4)
# the throat and chest folds are painted nearly as dark as the outline; close them only there
yy0,xx0=np.mgrid[0:H,0:W]
zone=(xx0>=270)&(xx0<=380)&(yy0>=230)&(yy0<=640)
core|=ndi.binary_closing(fur,structure=np.ones((3,3)),iterations=16)&zone
core|=poly([(900,518),(1065,518),(1050,600),(942,590),(915,560)])   # far thigh meets the belly
core|=poly([(118,180),(122,240),(132,262),(155,275),(190,281),(230,285),(262,281),(278,272),(300,262),(300,190)])   # dark lips and lower jaw
core=ndi.binary_fill_holes(core)
core=ndi.gaussian_filter(core.astype(np.float32),2.2)>.5   # smooth ragged edges everywhere, no hard corners
alpha_b=ndi.binary_dilation(core,iterations=2)          # take in the painted outline
ring=alpha_b&~core
alpha=ndi.gaussian_filter(alpha_b.astype(np.float32),0.8)
alpha=np.where(alpha_b,np.maximum(alpha,.5),alpha)
A=alpha_b

# ---- regions: 1 body, 2 head, 3 muzzle, 4 ears, 5 eye, 6 nose, 7 paws, 8 tail ----
reg=np.ones((H,W),np.uint8)
# head: nose side of the neck line (450,150)-(290,280)
P1,P2=np.array([450,150.]),np.array([290,280.]);d=P2-P1;nx,ny=-d[1],d[0]
side=(xx-P1[0])*nx+(yy-P1[1])*ny;ref=(143-P1[0])*nx+(175-P1[1])*ny
head=(np.sign(side)==np.sign(ref))&(yy<300)&(xx<470)
reg[head]=2
reg[poly([(95,120),(215,114),(245,165),(262,215),(275,292),(110,295)])]=3
reg[poly([(333,22),(358,14),(404,48),(424,100),(422,152),(388,152),(352,112),(330,62)])]=4
reg[poly([(272,58),(288,14),(306,10),(322,52),(302,78)])]=4
reg[ell(267,127,15,10)]=5
reg[nose]=6
paws=(poly([(205,875),(412,875),(412,1024),(205,1024)])|poly([(418,905),(612,905),(612,1024),(418,1024)])|
      poly([(1005,878),(1205,878),(1205,1024),(1005,1024)])|poly([(1285,898),(1435,898),(1435,1024),(1285,1024)]))
reg[paws]=7
# tail: the component past the tail-base line (1140,350)-(1200,475)
T1,T2=np.array([1140,350.]),np.array([1200,475.]);d=T2-T1;tnx,tny=-d[1],d[0]
tside=(xx-T1[0])*tnx+(yy-T1[1])*tny;tref=(1450-T1[0])*tnx+(497-T1[1])*tny
cand=A&(np.sign(tside)==np.sign(tref))&(yy<560)
lab,n=ndi.label(cand);tail=lab==lab[497,1450]
reg[tail]=8
reg[~A]=0

# ---- shading: match the painting's light to the bulldog master's shading range ----
bd1=np.array(body_map('bulldog_stack_v1',1).convert('RGB'));bd3=np.array(body_map('bulldog_stack_v1',3).convert('RGB'))
ref_vals=np.sort(bd1[...,0][bd3[...,0]>=128].astype(np.float32))
Ls=ndi.gaussian_filter(L,0.6)
v=Ls[A];order=np.argsort(v);q=np.empty_like(v);q[order]=np.linspace(0,1,len(v))
shade=np.zeros((H,W),np.float32)
matched=np.interp(q,np.linspace(0,1,len(ref_vals)),ref_vals)
own=np.clip(Ls[A]/255*1.38,0,1.6)*255/1.6
shade[A]=.45*matched+.55*own
# the eye and nose are painted near-black; lift them so iris colour and nose sheen survive
eyez=(reg==5);shade[eyez]=np.clip(.62+Ls[eyez]/255*1.4,0,1.6)*255/1.6
nz=(reg==6);shade[nz]=np.clip(.55+Ls[nz]/255*2.2,0,1.6)*255/1.6
shade[ring]=40
# patched-in areas (painted as background in the source) take the shading of the fur around them
edge=ndi.distance_transform_edt(A)
fill=A&(L<48)&(edge>4)&~np.isin(reg,[2,3,4,5,6])   # lips and face keep their painted darks
good=(A&~fill).astype(np.float32)
num=ndi.gaussian_filter(shade*good,14);den=ndi.gaussian_filter(good,14)+1e-6
shade[fill]=(num/den)[fill]*.85
shade[~A]=255
# ---- outline ink: the dark painted lines ----
ink=np.clip((70-L)/55,0,1)
ink=np.maximum(ink,np.clip((ndi.grey_closing(L,size=5)-L-60)/60,0,1)*.4)   # thin creases
ink[reg==6]*=.2;ink[reg==5]*=.45;ink[fill]=0;ink[ring]=1;ink[~A]=0
edt=ndi.distance_transform_edt(A);ink=np.where(A,np.maximum(ink,np.clip((5.8-edt)/1.6,0,1)),ink)   # outline as thick as the other masters so it holds up at card size
# ---- white-spread rank: low = turns white first, high = keeps color longest ----
rng=np.random.default_rng(7)
def fbm(s,oct=4):
    out=np.zeros((H,W),np.float32);amp=1
    for o in range(oct):
        g=rng.random((int(H/s)+2,int(W/s)+2)).astype(np.float32)
        out+=amp*np.array(Image.fromarray(g).resize((W,H),Image.BICUBIC));s/=2;amp*=.5
    return out
noise=fbm(180)
top=np.full(W,H);
for x in range(W):
    c=np.nonzero(A[:,x])[0]
    if len(c):top[x]=c[0]
depth=yy-top[None,:]
rank=.3+.35*(1-ss(0,380,depth))+.25*noise
rank-=.35*ss(640,820,yy)                       # legs go white first
rank[reg==3]-=.35;rank[reg==7]-=.5
rank-=.25*np.exp(-(((xx-330)/70)**2+((yy-470)/110)**2))   # chest
rank+=1.7*np.exp(-(((xx-318)/95)**2+((yy-108)/78)**2))    # classic head / ear patch
rank+=.45*np.exp(-(((xx-1090)/80)**2+((yy-400)/70)**2))   # croup spot
rank+=.3*np.exp(-(((xx-760)/90)**2+((yy-360)/70)**2))     # back spot
rank=ndi.gaussian_filter(rank,4)
wr=np.zeros((H,W),np.float32);v=rank[A];o=np.argsort(v);qq=np.empty_like(v);qq[o]=np.linspace(0,1,len(v));wr[A]=qq*255;wr[~A]=255

# ---- saddle field: back and tail ----
sad=(1-ss(0,230,depth))*ss(440,560,xx)*(reg==1)
sad=np.maximum(sad,(reg==8).astype(np.float32))
sad=ndi.gaussian_filter(sad,5)*A
# ---- tan points: brows, cheeks, chest, lower legs, under tail ----
tan=np.zeros((H,W),np.float32)
tan=np.maximum(tan,ell(255,98,16,11))
tan=np.maximum(tan,(reg==3)&(yy>205))
tan=np.maximum(tan,ell(318,440,34,58).astype(np.float32))
legs=(yy>650)&((xx<640)|(xx>900));tan=np.maximum(tan,legs*ss(700,820,yy))
tan=np.maximum(tan,ell(1175,480,22,16))
tan=ndi.gaussian_filter(tan.astype(np.float32),5)*A
# ---- facial mask field: muzzle, fading up to the eyes ----
mask=ndi.gaussian_filter(((reg==3)|(reg==6)).astype(np.float32),14)
mask=np.clip(mask*1.6,0,1)*(np.isin(reg,[2,3,5,6]))

def u8(a):return np.clip(np.round(a),0,255).astype(np.uint8)
m1=np.dstack([u8(shade),u8(ink*255),u8(wr)])
m2=np.dstack([u8(reg*20),u8(sad*255),u8(tan*255)])
m3=np.dstack([u8(alpha*255),u8(mask*255),np.zeros((H,W),np.uint8)])
def png(a):
    b=io.BytesIO();Image.fromarray(a,'RGB').save(b,'PNG',optimize=True);return 'data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()
new="dogo_stack_v1:{w:1536,h:1024,maps:{m1:'"+png(m1)+"',m2:'"+png(m2)+"',m3:'"+png(m3)+"'}}"
html,n=re.subn(r"dogo_stack_v1:\{w:1536,h:1024,maps:\{m1:'[^']*',m2:'[^']*',m3:'[^']*'\}\}",lambda m:new,html)
assert n==1,'dogo_stack_v1 entry not found in index.html'
open(INDEX,'w',encoding='utf-8').write(html)
print('dogo_stack_v1 rebuilt; regions',{int(k):int(v) for k,v in zip(*np.unique(reg[A],return_counts=True))})
