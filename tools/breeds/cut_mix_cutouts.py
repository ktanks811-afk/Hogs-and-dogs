# Cut each custom mix's own picture (assets/mixes/NNN_*.webp) out of its background for the hunt map and the 3D
# view: rembg finds the dog, the printed name and its outline are taken out, the picture is flipped to face left
# like every other dog picture in the game, trimmed, and saved as assets/mixes/cut/NNN.<hash>.webp with alpha.
# Prints the id -> path map used as MIXPIC.CUT.   Run: python3 tools/breeds/cut_mix_cutouts.py [ids...]
import os,io,re,sys,hashlib
import numpy as np
from PIL import Image,ImageOps
from scipy import ndimage as ndi
from rembg import remove,new_session
HERE=os.path.dirname(os.path.abspath(__file__));SRC=os.path.join(HERE,'..','..','assets','mixes');OUT=os.path.join(SRC,'cut');os.makedirs(OUT,exist_ok=True)
sess=new_session('isnet-general-use');only={int(x) for x in sys.argv[1:]};out={}
for f in sorted(os.listdir(SRC)):
    m=re.match(r'^(\d{3})_.*\.webp$',f)
    if not m:continue
    i=int(m.group(1))
    if only and i not in only:continue
    im=Image.open(os.path.join(SRC,f)).convert('RGB');a=np.array(im).astype(int);H,W=a.shape[:2]
    cut=np.array(remove(im,session=sess,post_process_mask=True)).astype(np.uint8);alpha=cut[...,3].astype(float)
    r,g,b=a[...,0],a[...,1],a[...,2]
    # the printed name: bright yellow title and white subtitle, low in the picture, plus their dark outline
    yel=(r>205)&(g>160)&(b<95)&(r-b>120);wht=(r>210)&(g>210)&(b>200)
    low=int(H*.55);rows=np.nonzero(yel[low:].sum(1)>10)[0]+low;top=rows.min()-3 if len(rows) else H
    txt=np.zeros((H,W),bool);txt[top:]=(yel|wht)[top:]
    # the letters' black outline: dark pixels hugging the letters
    lum=(r*3+g*6+b)/10;near=ndi.binary_dilation(txt,iterations=5)
    kill=ndi.binary_dilation(txt,iterations=1)|(near&(lum<95));kill=ndi.binary_closing(kill,iterations=1)
    alpha[kill]=0;alpha[ndi.binary_dilation(kill,iterations=1)]*=.4
    # thin leftovers along the text line
    band=np.zeros((H,W),bool);band[max(0,top-4):]=True;solid=ndi.binary_opening(alpha>100,structure=np.ones((3,3)),iterations=1);alpha[band&~solid]=0
    # keep the dog: the largest solid piece
    lab,n=ndi.label(alpha>100)
    if n>1:
        sizes=ndi.sum(np.ones_like(alpha),lab,range(1,n+1));keep=np.argmax(sizes)+1;alpha[(lab!=keep)&(lab>0)]=0
    rgba=np.dstack([a.astype(np.uint8),alpha.clip(0,255).astype(np.uint8)])
    pic=ImageOps.mirror(Image.fromarray(rgba,'RGBA'));bb=pic.getbbox();pic=pic.crop(bb)
    buf=io.BytesIO();pic.save(buf,'WEBP',quality=90,method=6);d=buf.getvalue()
    fn=f'{i:03d}.{hashlib.sha1(d).hexdigest()[:8]}.webp'
    for old in os.listdir(OUT):
        if old.startswith(f'{i:03d}.'):os.remove(os.path.join(OUT,old))
    open(os.path.join(OUT,fn),'wb').write(d);out[i]='/assets/mixes/cut/'+fn
print('CUT:{'+','.join(f"{k}:'{v}'" for k,v in sorted(out.items()))+'}')
