# Picture breeds: a purebred whose look is a supplied picture, not a painted master.
# tools/breeds/<slug>_reference.png -> the dog cut out of its background (rembg), trimmed, facing left like every dog in
# the game, saved with transparency as assets/breeds/<slug>.<hash>.webp (cards, profile, hunt map and 3D all use it).
# Run: python3 tools/breeds/breed_pictures.py german_rottweiler    (rembg, scipy, pillow)
import os,io,sys,glob,hashlib
import numpy as np
from PIL import Image
from rembg import remove,new_session
from scipy import ndimage as ndi
HERE=os.path.dirname(os.path.abspath(__file__));OUT=os.path.join(HERE,'..','..','assets','breeds');os.makedirs(OUT,exist_ok=True)
s=new_session('isnet-general-use')
for slug in sys.argv[1:]:
    im=Image.open(os.path.join(HERE,slug+'_reference.png')).convert('RGB')
    c=np.array(remove(im,session=s,post_process_mask=True));a=c[...,3]>100;lab,n=ndi.label(a)
    if n>1:sz=ndi.sum(a,lab,range(1,n+1));c[...,3][lab!=np.argmax(sz)+1]=0
    p=Image.fromarray(c,'RGBA');p=p.crop(p.getbbox());p.thumbnail((720,560),Image.LANCZOS)
    buf=io.BytesIO();p.save(buf,'WEBP',quality=90,method=6);d=buf.getvalue()
    for old in glob.glob(os.path.join(OUT,slug+'.*')):os.remove(old)
    fn=f'{slug}.{hashlib.sha1(d).hexdigest()[:8]}.webp';open(os.path.join(OUT,fn),'wb').write(d);print(slug,'/assets/breeds/'+fn,p.size)
