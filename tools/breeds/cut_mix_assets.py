# Cut one picture per custom mix out of the 90-dog reference sheet (tools/breeds/mix_sheet_reference.png) into
# assets/mixes/NNN_name.<hash>.webp, and print the id -> assetPath map used by the recipe database (MIX.ASSETS).
# Each tile is located from its own yellow name label (the sheet's grid isn't even: columns ~151.5 px apart and rows
# drift), so every picture shows its own dog and label. Names come from tools/breeds/breed_recipes.csv.
# Run:  python3 tools/breeds/cut_mix_assets.py    (pillow, numpy, scipy)
import os,io,csv,re,hashlib
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
HERE=os.path.dirname(os.path.abspath(__file__));OUT=os.path.join(HERE,'..','..','assets','mixes');os.makedirs(OUT,exist_ok=True)
names={int(r['id']):r['name'] for r in csv.DictReader(open(os.path.join(HERE,'breed_recipes.csv')))}
src=Image.open(os.path.join(HERE,'mix_sheet_reference.png')).convert('RGB');im=np.array(src).astype(int)
r,g,b=im[...,0],im[...,1],im[...,2];yel=(r>200)&(g>150)&(b<90)&(r-b>130)
rows=np.nonzero(yel.sum(1)>40)[0];runs=[];s0=p=rows[0]
for y in rows[1:]:
    if y-p>6:runs.append((s0,p));s0=y
    p=y
runs.append((s0,p));assert len(runs)==9,runs
for f in os.listdir(OUT):
    if re.match(r'^\d{3}_',f) or f.startswith('sheet-'):os.remove(os.path.join(OUT,f))
TW,TH=150,112;out={}
for ri,(a,bb) in enumerate(runs):
    band=yel[a:bb+1].sum(0)>0;lab,n=ndi.label(ndi.binary_dilation(band,iterations=6));assert n==10,(ri,n)
    ly=(a+bb)//2
    for ci in range(10):
        i=ri*10+ci+1;cx=int(np.mean(np.nonzero(lab==ci+1)[0]));x0=min(max(0,cx-TW//2),src.width-TW);y0=min(max(0,ly-92),src.height-TH)
        tile=src.crop((x0,y0,x0+TW,y0+TH)).resize((TW*2,TH*2),Image.LANCZOS)
        buf=io.BytesIO();tile.save(buf,'WEBP',quality=86,method=6);d=buf.getvalue()
        slug=re.sub(r'[^a-z0-9]+','_',names[i].lower()).strip('_')
        fn=f'{i:03d}_{slug}.{hashlib.sha1(d).hexdigest()[:8]}.webp';open(os.path.join(OUT,fn),'wb').write(d);out[i]='/assets/mixes/'+fn
print('ASSETS:{'+','.join(f"{k}:'{v}'" for k,v in sorted(out.items()))+'}')
