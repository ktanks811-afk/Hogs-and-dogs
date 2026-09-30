# Hunt-map / 3D pictures for the custom mixes, cut from the unlabelled 72-dog sheet (tools/breeds/mix_sheet_nolabels.png)
# so every dog keeps its whole legs (the labelled sheet prints each name across the dog's feet).
#  1. rembg finds the dogs; the sheet is split into 8 rows and 9 dogs per row at the gaps between them.
#  2. Each dog is cut from its own box at 3x and trimmed.
#  3. Each is matched to the mix it shows by coat colour and markings (one dog per mix, best overall fit); mixes with
#     no dog of their own on this sheet take the closest-coloured one.
#  4. Flipped to face left like every dog picture in the game and saved as assets/mixes/cut/NNN.<hash>.webp.
#  5. Each mix with its own dog also gets a clean card picture (assets/mixes/card/NNN.<hash>.webp): that one whole dog on
#     a soft backdrop, with none of the neighbouring dogs' halves and no printed name.
# Prints the id -> path maps used as MIXPIC.CARD and MIXPIC.CUT.   Run: python3 tools/breeds/cut_mix_legs.py  (rembg, scipy, pillow)
import os,io,re,glob,hashlib
import numpy as np
from PIL import Image,ImageOps
from rembg import remove,new_session
from scipy import ndimage as ndi
from scipy.optimize import linear_sum_assignment
HERE=os.path.dirname(os.path.abspath(__file__));MIX=os.path.join(HERE,'..','..','assets','mixes');OUT=os.path.join(MIX,'cut')
FIX={57:(560,780,735,925),64:(165,905,360,1024)}   # two dogs whose neighbours touch them get a hand-set box
im=Image.open(os.path.join(HERE,'mix_sheet_nolabels.png')).convert('RGB');W,H=im.size;s=new_session('isnet-general-use')
mask=np.zeros((H,W),np.uint8)
for x0,y0 in [(0,0),(700,0),(0,470),(700,470)]:
    x1,y1=min(W,x0+836),min(H,y0+554);mask[y0:y1,x0:x1]=np.maximum(mask[y0:y1,x0:x1],np.array(remove(im.crop((x0,y0,x1,y1)),session=s,only_mask=True)))
m=(mask>110).astype(float)
def cuts(prof,n,L):
    out=[];step=L/n
    for k in range(1,n):c=int(k*step);w=int(step*.35);out.append(c-w+int(np.argmin(prof[c-w:c+w])))
    return [0]+out+[L]
ry=cuts(ndi.uniform_filter1d(m.sum(1),9),8,H);boxes=[]
for r in range(8):
    cx=cuts(ndi.uniform_filter1d(m[ry[r]:ry[r+1]].sum(0),7),9,W)
    for c in range(9):boxes.append((max(0,cx[c]-4),max(0,ry[r]-4),min(W,cx[c+1]+4),min(H,ry[r+1]+4)))
def cutout(box):
    x0,y0,x1,y1=box;c=np.array(remove(im.crop(box).resize(((x1-x0)*3,(y1-y0)*3),Image.LANCZOS),session=s,post_process_mask=True))
    a=c[...,3]>100;lab,n=ndi.label(a)
    if n>1:sz=ndi.sum(a,lab,range(1,n+1));c[...,3][lab!=np.argmax(sz)+1]=0
    p=Image.fromarray(c,'RGBA');return p.crop(p.getbbox())
dogs=[cutout(FIX.get(i,b)) for i,b in enumerate(boxes)]
def feats(p):
    # coat classes (black, white, grey/blue, red/tan, dark red), how mottled it is (merle/brindle), and where the colours sit
    a=np.array(p.resize((96,int(96*p.height/p.width)),Image.LANCZOS)).astype(float);al=a[...,3]>128
    hsv=np.array(Image.fromarray(a[...,:3].astype(np.uint8)).convert('HSV')).astype(float);Hh,S,V=hsv[...,0],hsv[...,1],hsv[...,2]
    cls=np.stack([V<55,(S<50)&(V>165),(S<70)&(V>=55)&(V<=165),(S>=70)&(V>120),(S>=70)&(V>=55)&(V<=120)],-1)&al[...,None]
    frac=cls.sum((0,1))/max(1,al.sum())
    lum=V/255;mu=ndi.uniform_filter(lum,5);sd=np.sqrt(np.clip(ndi.uniform_filter(lum*lum,5)-mu*mu,0,None));tex=np.array([sd[al].mean(),np.percentile(sd[al],80)])
    ys,xs=np.nonzero(al);y0,y1,x0,x1=ys.min(),ys.max()+1,xs.min(),xs.max()+1;lay=[]
    for gy in range(3):
        for gx in range(4):
            c=cls[y0+(y1-y0)*gy//3:y0+(y1-y0)*(gy+1)//3,x0+(x1-x0)*gx//4:x0+(x1-x0)*(gx+1)//4];n=max(1,c.any(-1).sum());lay.append(c.sum((0,1))/n)
    return frac,tex,np.concatenate(lay)
# each mix's own picture with the background and printed name taken out (the same steps as cut_mix_cutouts.py),
# as the thing to match against
def ref(p):
    a=np.array(p).astype(int);Hh=a.shape[0];c=np.array(remove(p,session=s,post_process_mask=True));al=c[...,3].astype(float);r_,g_,b_=a[...,0],a[...,1],a[...,2]
    yel=(r_>205)&(g_>160)&(b_<95)&(r_-b_>120);wht=(r_>210)&(g_>210)&(b_>200);low=int(Hh*.55);rows=np.nonzero(yel[low:].sum(1)>10)[0]+low;top=rows.min()-3 if len(rows) else Hh
    al[max(0,top-2):]=0;c[...,3]=al.clip(0,255).astype(np.uint8);q=Image.fromarray(c,'RGBA');return q.crop(q.getbbox())
refs={}
for f in sorted(os.listdir(MIX)):
    mm=re.match(r'^(\d{3})_.*\.webp$',f)
    if mm:refs[int(mm.group(1))]=ref(Image.open(os.path.join(MIX,f)).convert('RGB'))
ids=sorted(refs);F=[feats(d) for d in dogs];G=[feats(refs[i]) for i in ids]
C=np.array([[np.abs(a[0]-b[0]).sum()*2+np.abs(a[1]-b[1]).sum()*6+np.abs(a[2]-b[2]).mean()*3 for b in G] for a in F])
r,c=linear_sum_assignment(C);pick={ids[j]:i for i,j in zip(r,c)}
for j,mid in enumerate(ids):
    if mid not in pick:pick[mid]=int(np.argmin(C[:,j]))
own={ids[j]:int(i) for i,j in zip(r,c)}
# a clean card picture for each mix that has its own dog on the sheet: the whole dog on a soft backdrop, nothing else
CARD=os.path.join(MIX,'card');os.makedirs(CARD,exist_ok=True);cards={}
yy,xx=np.mgrid[0:224,0:300];rad=np.clip(np.hypot((xx-150)/190,(yy-100)/150),0,1)[...,None]
bgA=(np.array([176,150,126])*(1-rad)+np.array([92,78,68])*rad).astype(np.uint8)
for mid,i in sorted(own.items()):
    bg=Image.fromarray(np.dstack([bgA,np.full((224,300),255,np.uint8)]),'RGBA');d=ImageOps.mirror(dogs[i]);d.thumbnail((270,196),Image.LANCZOS)
    sh=Image.new('RGBA',(300,224),(0,0,0,0));from PIL import ImageDraw,ImageFilter;ImageDraw.Draw(sh).ellipse((150-d.width*.42,212-10,150+d.width*.42,212+8),fill=(0,0,0,90));bg.alpha_composite(sh.filter(ImageFilter.GaussianBlur(5)))
    bg.alpha_composite(d,((300-d.width)//2,214-d.height));buf=io.BytesIO();bg.convert('RGB').save(buf,'WEBP',quality=88,method=6);dd=buf.getvalue()
    for old in glob.glob(os.path.join(CARD,f'{mid:03d}.*')):os.remove(old)
    fn=f'{mid:03d}.{hashlib.sha1(dd).hexdigest()[:8]}.webp';open(os.path.join(CARD,fn),'wb').write(dd);cards[mid]='/assets/mixes/card/'+fn
print('CARD:{'+','.join(f"{k}:'{v}'" for k,v in sorted(cards.items()))+'}')
out={}
for mid,i in sorted(pick.items()):
    p=ImageOps.mirror(dogs[i]);p.thumbnail((360,300),Image.LANCZOS);buf=io.BytesIO();p.save(buf,'WEBP',quality=90,method=6);d=buf.getvalue()
    for old in glob.glob(os.path.join(OUT,f'{mid:03d}.*')):os.remove(old)
    fn=f'{mid:03d}.{hashlib.sha1(d).hexdigest()[:8]}.webp';open(os.path.join(OUT,fn),'wb').write(d);out[mid]='/assets/mixes/cut/'+fn
print('CUT:{'+','.join(f"{k}:'{v}'" for k,v in sorted(out.items()))+'}')
