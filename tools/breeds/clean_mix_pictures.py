# Each custom mix's own picture (assets/mixes/NNN_name.<hash>.webp, cut from the reference sheet), made clean for the game:
#  card: the picture exactly as drawn, name and parents line included, with the halves of neighbouring dogs and their
#        stray letters (the sheet's tiles overlap) painted out of the smooth background.  -> assets/mixes/card/NNN.<hash>.webp
#  cut:  the same dog cut out of its background for the hunt map and 3D: the printed name is taken off, the legs it covered
#        are carried on down to the ground, and the dog is flipped to face left like every dog in the game.
#                                                                                         -> assets/mixes/cut/NNN.<hash>.webp
# Prints the id -> path maps used as MIXPIC.CARD and MIXPIC.CUT.
# Run: python3 tools/breeds/clean_mix_pictures.py   (rembg, opencv-python-headless, scipy, pillow)
import os,io,re,glob,hashlib
import numpy as np,cv2
from PIL import Image,ImageOps
from rembg import remove,new_session
from scipy import ndimage as ndi
HERE=os.path.dirname(os.path.abspath(__file__));MIX=os.path.join(HERE,'..','..','assets','mixes')
s=new_session('isnet-general-use')
def save(img,folder,mid,fmt):
    os.makedirs(os.path.join(MIX,folder),exist_ok=True);buf=io.BytesIO();img.save(buf,'WEBP',quality=90,method=6);d=buf.getvalue()
    for old in glob.glob(os.path.join(MIX,folder,f'{mid:03d}.*')):os.remove(old)
    fn=f'{mid:03d}.{hashlib.sha1(d).hexdigest()[:8]}.webp';open(os.path.join(MIX,folder,fn),'wb').write(d);return f'/assets/mixes/{folder}/{fn}'
def card(im):
    a=np.array(im);H,W=a.shape[:2];r,g,b=[a[...,k].astype(int) for k in range(3)];lum=(r*3+g*6+b)/10
    m=np.array(remove(im,session=s,only_mask=True))>100
    yel=(r>190)&(g>140)&(b<110)&(r-b>100);wht=(r>205)&(g>205)&(b>195)
    # the mix's own name and parents line: text clusters near the bottom whose centre sits in the middle of the picture
    T=(yel|wht);T[:int(H*.55)]=False;tl,tn=ndi.label(ndi.binary_dilation(T,structure=np.ones((3,15))));keep=np.zeros((H,W),bool)
    for k in range(1,tn+1):
        ys,xs=np.nonzero(tl==k)
        if len(ys)<15:continue
        if W*.25<(xs.min()+xs.max())/2<W*.75:keep[max(0,ys.min()-5):min(H,ys.max()+6),max(0,xs.min()-6):min(W,xs.max()+7)]=True
    lab,n=ndi.label(m);dog=np.zeros((H,W),bool)
    if n:sz=ndi.sum(m,lab,range(1,n+1));dog=lab==np.argmax(sz)+1
    # everything else that stands out: a neighbour's half dog, its letters, the row above's label along the top edge
    other=(m&~dog)|((yel|wht)&~keep);top=np.zeros((H,W),bool);top[:int(H*.1)]=True;other|=top&((yel|wht)|(lum<45))&~dog
    other=ndi.binary_dilation(other,iterations=3)&~ndi.binary_dilation(dog,iterations=1)&~keep
    out=cv2.inpaint(a[...,::-1].copy(),other.astype(np.uint8)*255,7,cv2.INPAINT_TELEA)[...,::-1] if other.any() else a
    return Image.fromarray(out)
def cutout(im,up=2):
    W,H=im.size;im=im.resize((W*up,H*up),Image.LANCZOS);a=np.array(im);H2=a.shape[0];r,g,b=[a[...,k].astype(int) for k in range(3)]
    yel=(r>205)&(g>160)&(b<95)&(r-b>120);low=int(H2*.55);rows=np.nonzero(yel[low:].sum(1)>10*up)[0]+low;top=(rows.min()-4*up) if len(rows) else H2
    c=np.array(remove(im,session=s,post_process_mask=True));al=c[...,3].copy();al[top:]=0
    lab,n=ndi.label(al>100)
    if n>1:sz=ndi.sum(al>100,lab,range(1,n+1));al[lab!=np.argmax(sz)+1]=0
    if top<H2:
        # carry the legs on below the name: stretch the last bit of leg down to the ground, feet softened
        L=12*up;E=int((H2-top)*.5);out=a.copy();oal=al.copy()
        for y in range(top-L,min(H2,top+E)):sy=int(top-L+(y-(top-L))*L/(L+E));out[y]=a[sy];oal[y]=al[sy]
        a,al=out,oal
        for k in range(3*up):y=min(H2-1,top+E-1-k);al[y]=(al[y]*(k/(3*up))).astype(al.dtype)
    o=ImageOps.mirror(Image.fromarray(np.dstack([a,al]).astype(np.uint8),'RGBA'));return o.crop(o.getbbox())
cards,cuts={},{}
for f in sorted(os.listdir(MIX)):
    mm=re.match(r'^(\d{3})_.*\.webp$',f)
    if not mm:continue
    mid=int(mm.group(1));im=Image.open(os.path.join(MIX,f)).convert('RGB');cl=card(im)
    cards[mid]=save(cl,'card',mid,'webp');cuts[mid]=save(cutout(cl),'cut',mid,'webp')
print('CARD:{'+','.join(f"{k}:'{v}'" for k,v in sorted(cards.items()))+'}')
print('CUT:{'+','.join(f"{k}:'{v}'" for k,v in sorted(cuts.items()))+'}')
