# Build the Cane Corso master stack (m1/m2/m3) from the reference image, in the same channel layout the
# coat engine uses for every other body, and embed it in index.html as corso_stack_v1.
#   m1 = shading | outline ink | white-spread rank
#   m2 = region id x20 (1 body 2 head 3 muzzle 4 ears 5 eye 6 nose 7 paws 8 tail) | saddle field | tan-point field
#   m3 = alpha | facial-mask field | coat length (0 = short)
# Run from anywhere:  python3 tools/corso/build_corso_master.py   (needs pillow, numpy, scipy)
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
src=np.array(Image.open(os.path.join(HERE,'corso_reference.png')).convert('RGB')).astype(np.float32)
L=src.mean(2)
yy,xx=np.mgrid[0:H,0:W]
def poly(pts):
    im=Image.new('L',(W,H),0);ImageDraw.Draw(im).polygon(pts,fill=255);return np.array(im)>0
def ell(cx,cy,rx,ry):return ((xx-cx)/rx)**2+((yy-cy)/ry)**2<=1
def ss(a,b,x):t=np.clip((x-a)/(b-a),0,1);return t*t*(3-2*t)

# ---- alpha: the dog is dark gray on a near-black backdrop with a soft glow; fur has fine texture, the glow doesn't ----
det=ndi.gaussian_filter(np.abs(L-ndi.gaussian_filter(L,2.5)),2)
fur=(det>1.3)&(L>14)
fur=ndi.binary_opening(fur,iterations=2)
lab,n=ndi.label(fur);sizes=ndi.sum(fur,lab,range(1,n+1));fur=np.isin(lab,1+np.nonzero(sizes>8000)[0])
core=ndi.binary_fill_holes(ndi.binary_closing(fur,iterations=5))
core=ndi.binary_opening(core,iterations=3)
core=ndi.gaussian_filter(core.astype(np.float32),2.5)>.5
alpha_b=ndi.binary_dilation(core,iterations=1)
ring=alpha_b&~ndi.binary_erosion(core,iterations=1)
alpha=ndi.gaussian_filter(alpha_b.astype(np.float32),0.8)
alpha=np.where(alpha_b,np.maximum(alpha,.5),alpha)
A=alpha_b

# ---- regions ----
reg=np.ones((H,W),np.uint8)
P1,P2=np.array([545,120.]),np.array([420,320.]);d=P2-P1;nx,ny=-d[1],d[0]
side=(xx-P1[0])*nx+(yy-P1[1])*ny;ref=(300-P1[0])*nx+(178-P1[1])*ny
head=(np.sign(side)==np.sign(ref))&(yy<330)&(xx<560)
reg[head]=2
reg[poly([(268,160),(300,146),(345,150),(372,190),(385,240),(368,288),(312,302),(272,288),(260,232)])]=3
reg[poly([(333,62),(343,22),(360,12),(378,38),(388,62)])&A]=4
reg[poly([(438,58),(468,16),(496,12),(526,58),(546,108),(538,142),(515,132),(480,92)])&A]=4
eyes=ell(300,137,10,8)|ell(401,137,14,9)
reg[eyes]=5
nose=ell(302,177,30,23)&(ndi.gaussian_filter(L,1.5)<70)
nose=ndi.binary_fill_holes(ndi.binary_closing(nose,iterations=2))
reg[nose]=6
paws=(poly([(270,880),(445,880),(445,960),(270,960)])|poly([(505,905),(650,905),(650,990),(505,990)])|
      poly([(985,872),(1115,872),(1115,950),(985,950)])|poly([(1268,895),(1390,895),(1390,975),(1268,975)]))
reg[paws&A]=7
T1,T2=np.array([1112,300.]),np.array([1128,395.]);d=T2-T1;tnx,tny=-d[1],d[0]
tside=(xx-T1[0])*tnx+(yy-T1[1])*tny;tref=(1160-T1[0])*tnx+(340-T1[1])*tny
cand=A&(np.sign(tside)==np.sign(tref))&(yy<400)&(yy>290)
lab,n=ndi.label(cand);tail=lab==lab[340,1160]
reg[tail]=8
reg[~A]=0

# ---- shading: the photo's light, remapped into the bulldog master's shading range ----
bd1=np.array(body_map('bulldog_stack_v1',1).convert('RGB'));bd3=np.array(body_map('bulldog_stack_v1',3).convert('RGB'))
ref_vals=np.sort(bd1[...,0][bd3[...,0]>=128].astype(np.float32))
Ls=ndi.gaussian_filter(L,0.6)
# the white chest blaze is a colour, not light: shade it like the fur around it
blaze=A&(Ls>150)&ell(430,505,75,90)
blaze=ndi.binary_dilation(blaze,iterations=3)&A
good=(A&~blaze).astype(np.float32)
Lf=Ls.copy();fillv=ndi.gaussian_filter(Ls*good,10)/(ndi.gaussian_filter(good,10)+1e-6);Lf[blaze]=fillv[blaze]
v=Lf[A];order=np.argsort(v);q=np.empty_like(v);q[order]=np.linspace(0,1,len(v))
shade=np.zeros((H,W),np.float32)
matched=np.interp(q,np.linspace(0,1,len(ref_vals)),ref_vals)
own=np.clip(Lf[A]/110,0,1.6)*255/1.6
shade[A]=.5*matched+.5*own
eyez=(reg==5);shade[eyez]=np.clip(.62+Ls[eyez]/255*1.4,0,1.6)*255/1.6
nz=(reg==6);shade[nz]=np.clip(.55+Ls[nz]/255*2.2,0,1.6)*255/1.6
shade[ring]=40
shade[~A]=255
# ---- outline ink: the dark creases and wrinkles of the photo, plus a solid outline ----
ink=np.clip((22-Lf)/18,0,1)*.8
ink=np.maximum(ink,np.clip((ndi.grey_closing(Lf,size=5)-Lf-18)/30,0,1)*.45)
ink[reg==6]*=.2;ink[reg==5]*=.45;ink[blaze]=0;ink[ring]=1;ink[~A]=0
edt=ndi.distance_transform_edt(A);ink=np.where(A,np.maximum(ink,np.clip((5.8-edt)/1.6,0,1)),ink)
# ---- white-spread rank: low = turns white first. Corso white starts at the chest blaze, then the toes ----
rng=np.random.default_rng(11)
def fbm(s,oct=4):
    out=np.zeros((H,W),np.float32);amp=1
    for o in range(oct):
        g=rng.random((int(H/s)+2,int(W/s)+2)).astype(np.float32)
        out+=amp*np.array(Image.fromarray(g).resize((W,H),Image.BICUBIC));s/=2;amp*=.5
    return out
noise=fbm(180)
top=np.full(W,H)
for x in range(W):
    c=np.nonzero(A[:,x])[0]
    if len(c):top[x]=c[0]
depth=yy-top[None,:]
rank=.45+.3*(1-ss(0,380,depth))+.2*noise
rank-=.3*ss(760,900,yy)
rank[reg==7]-=.55
rank-=.75*np.exp(-(((xx-432)/42)**2+((yy-505)/70)**2))     # chest blaze
rank-=.3*np.exp(-(((xx-470)/80)**2+((yy-590)/60)**2))      # down the brisket
headish=ndi.gaussian_filter(np.isin(reg,[2,3,4,5,6]).astype(np.float32),22)
rank+=.45*headish+.2*(reg==4)                              # the head keeps its colour longest (soft edge down the neck)
rank=ndi.gaussian_filter(rank,4)
wr=np.zeros((H,W),np.float32);v=rank[A];o=np.argsort(v);qq=np.empty_like(v);qq[o]=np.linspace(0,1,len(v));wr[A]=qq*255;wr[~A]=255
# ---- saddle field: back and tail ----
sad=(1-ss(0,210,depth))*ss(520,640,xx)*(reg==1)
sad=np.maximum(sad,(reg==8).astype(np.float32))
sad=ndi.gaussian_filter(sad,5)*A
# ---- tan points: brows, cheeks, chest, lower legs, under the tail ----
tan=np.zeros((H,W),np.float32)
tan=np.maximum(tan,ell(300,118,14,9)|ell(402,116,17,9))
tan=np.maximum(tan,(reg==3)&(yy>215))
tan=np.maximum(tan,ell(432,500,40,62).astype(np.float32))
legs=(yy>700)&((xx<700)|(xx>950));tan=np.maximum(tan,legs*ss(730,850,yy))
tan=np.maximum(tan,ell(1125,385,18,14))
tan=ndi.gaussian_filter(tan.astype(np.float32),5)*A
# ---- facial mask: muzzle and flews, fading up past the eyes (the Corso's mask) ----
mask=ndi.gaussian_filter(((reg==3)|(reg==6)).astype(np.float32),16)
mask=np.clip(mask*1.7,0,1)*(np.isin(reg,[2,3,5,6]))

def u8(a):return np.clip(np.round(a),0,255).astype(np.uint8)
m1=np.dstack([u8(shade),u8(ink*255),u8(wr)])
m2=np.dstack([u8(reg*20),u8(sad*255),u8(tan*255)])
m3=np.dstack([u8(alpha*255),u8(mask*255),np.zeros((H,W),np.uint8)])
def png(a):
    b=io.BytesIO();Image.fromarray(a,'RGB').save(b,'PNG',optimize=True);return 'data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()
new="corso_stack_v1:{w:1536,h:1024,maps:{m1:'"+png(m1)+"',m2:'"+png(m2)+"',m3:'"+png(m3)+"'}}"
pat=r"corso_stack_v1:\{w:1536,h:1024,maps:\{m1:'[^']*',m2:'[^']*',m3:'[^']*'\}\}"
if re.search(pat,html):html=re.sub(pat,lambda m:new,html)
else:
    dm=re.search(r"dogo_stack_v1:\{w:1536,h:1024,maps:\{m1:'[^']*',m2:'[^']*',m3:'[^']*'\}\}",html);assert dm,'dogo_stack_v1 not found'
    html=html[:dm.end()]+",\n  "+new+html[dm.end():]
open(INDEX,'w',encoding='utf-8').write(html)
print('corso_stack_v1 built; regions',{int(k):int(v) for k,v in zip(*np.unique(reg[A],return_counts=True))})
