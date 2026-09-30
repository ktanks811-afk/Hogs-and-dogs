# The custom mixes' own dogs: tools/breeds/mix_sheet_dogs.png is 73 whole dogs in recipe order, read left to right,
# 9 to a row with 10 in the last row (dog 1 is mix #1 Bully, dog 66 is mix #66 Honey Cur, dog 73 is mix #73 Stone Hound).
# (The recipe chart's thumbnails slice this sheet as if it were 10 to a row, which is why they show half dogs.)
#  1. rembg finds the dogs. Rows 1-6: each dog grows out from its body core (watershed), so a head or tail reaching
#     past the gap stays with its own dog. Rows 7-8 are crowded, so each dog there has a hand-set box.
#  2. Each dog is cut at 3x and trimmed.
#  3. card: that whole dog on a soft backdrop -> assets/mixes/card/NNN.<hash>.webp (cards, profile, Discovery Book)
#     cut:  the same dog flipped to face left like every dog in the game -> assets/mixes/cut/NNN.<hash>.webp (hunt map, 3D)
# Mixes after #73 have no dog on this sheet and keep the pictures from clean_mix_pictures.py.
# Prints the id -> path maps for MIXPIC.CARD and MIXPIC.CUT (merge them over the existing ones).
# Run: python3 tools/breeds/mix_sheet_pictures.py   (rembg, scipy, pillow)
import os,io,re,glob,hashlib
import numpy as np
from PIL import Image,ImageOps
from rembg import remove,new_session
from scipy import ndimage as ndi
from scipy.optimize import linear_sum_assignment
HERE=os.path.dirname(os.path.abspath(__file__));MIX=os.path.join(HERE,'..','..','assets','mixes');OUT=os.path.join(MIX,'cut')
im=Image.open(os.path.join(HERE,'mix_sheet_dogs.png')).convert('RGB');W,H=im.size;s=new_session('isnet-general-use')
mask=np.zeros((H,W),np.uint8)
for x0,y0 in [(0,0),(700,0),(0,470),(700,470)]:
    x1,y1=min(W,x0+836),min(H,y0+554);mask[y0:y1,x0:x1]=np.maximum(mask[y0:y1,x0:x1],np.array(remove(im.crop((x0,y0,x1,y1)),session=s,only_mask=True)))
m=(mask>110).astype(float);m=ndi.binary_opening(m>0,iterations=1).astype(float)
def cuts(prof,n,L):
    out=[];step=L/n
    for k in range(1,n):c=int(k*step);w=int(step*.35);out.append(c-w+int(np.argmin(prof[c-w:c+w])))
    return [0]+out+[L]
from skimage.segmentation import watershed
# rows 1-6 sit on an even grid: each dog grows out from its thick body core, so a head or tail past the gap stays with it
mb=ndi.binary_opening(mask>110,iterations=1);dt=ndi.distance_transform_edt(mb);core,nc=ndi.label(dt>6)
sz=ndi.sum(dt>6,core,range(1,nc+1));keep=[k+1 for k in range(nc) if sz[k]>150];cen=ndi.center_of_mass(dt>6,core,keep)
cores=sorted(zip(keep,cen),key=lambda t:t[1][0]);grid=[sorted(cores[r*9:(r+1)*9],key=lambda t:t[1][1]) for r in range(6)]
mk=np.zeros((H,W),int)
for r,row in enumerate(grid):
    for c,(k,_) in enumerate(row):mk[core==k]=r*9+c+1
ws=watershed(-dt,mk,mask=mb)
# rows 7-8 are crowded and uneven (the last row has 10 dogs): each dog has its own hand-set box
BOX=[(5,772,178,920),(192,772,398,920),(398,772,580,920),(572,772,742,920),(738,772,908,920),(902,772,1062,920),(1058,772,1216,920),(1210,772,1372,920),(1366,772,1536,920),
     (0,902,178,1024),(170,902,338,1024),(330,902,498,1024),(482,902,662,1024),(622,902,792,1024),(778,902,938,1024),(922,902,1082,1024),(1066,902,1218,1024),(1196,902,1372,1024),(1364,902,1536,1024)]
def finish(c,keepmask=None):
    if keepmask is not None:c[...,3][~keepmask]=0
    a=c[...,3]>100;lb,nn=ndi.label(a)
    if nn>1:
        sz=ndi.sum(a,lb,range(1,nn+1));cy,cx=np.array(a.shape)/2
        # the dog is the big piece nearest the middle of its box
        cm=ndi.center_of_mass(a,lb,range(1,nn+1));score=[sz[j]-3*np.hypot(cm[j][0]-cy,cm[j][1]-cx)*0 for j in range(nn)]
        big=[j for j in range(nn) if sz[j]>.35*sz.max()];j=min(big,key=lambda j:abs(cm[j][1]-cx))
        c[...,3][lb!=j+1]=0
    p=Image.fromarray(c,'RGBA');return p.crop(p.getbbox())
def cut_grid(i):
    ys,xs=np.nonzero(ws==i+1);x0,y0,x1,y1=max(0,xs.min()-8),max(0,ys.min()-8),min(W,xs.max()+9),min(H,ys.max()+9)
    c=np.array(remove(im.crop((x0,y0,x1,y1)).resize(((x1-x0)*3,(y1-y0)*3),Image.LANCZOS),session=s,post_process_mask=True))
    mine=ndi.binary_dilation(ws[y0:y1,x0:x1]==i+1,iterations=3);km=np.array(Image.fromarray(mine.astype(np.uint8)*255).resize(((x1-x0)*3,(y1-y0)*3),Image.NEAREST))>0
    return finish(c,km)
def cut_box(b):
    x0,y0,x1,y1=b;c=np.array(remove(im.crop(b).resize(((x1-x0)*3,(y1-y0)*3),Image.LANCZOS),session=s,post_process_mask=True));return finish(c)
dogs=[cut_grid(i) for i in range(54)]+[cut_box(b) for b in BOX]
from PIL import ImageDraw,ImageFilter
def save(img,folder,mid):
    buf=io.BytesIO();img.save(buf,'WEBP',quality=90,method=6);d=buf.getvalue()
    for old in glob.glob(os.path.join(MIX,folder,f'{mid:03d}.*')):os.remove(old)
    fn=f'{mid:03d}.{hashlib.sha1(d).hexdigest()[:8]}.webp';open(os.path.join(MIX,folder,fn),'wb').write(d);return f'/assets/mixes/{folder}/{fn}'
yy,xx=np.mgrid[0:224,0:300];rad=np.clip(np.hypot((xx-150)/190,(yy-100)/150),0,1)[...,None]
bgA=(np.array([176,150,126])*(1-rad)+np.array([92,78,68])*rad).astype(np.uint8)
cards,cuts={},{}
for i,d in enumerate(dogs):
    mid=i+1;bg=Image.fromarray(np.dstack([bgA,np.full((224,300),255,np.uint8)]),'RGBA');c=d.copy();c.thumbnail((270,196),Image.LANCZOS)
    sh=Image.new('RGBA',(300,224),(0,0,0,0));ImageDraw.Draw(sh).ellipse((150-c.width*.42,202,150+c.width*.42,220),fill=(0,0,0,90));bg.alpha_composite(sh.filter(ImageFilter.GaussianBlur(5)))
    bg.alpha_composite(c,((300-c.width)//2,214-c.height));cards[mid]=save(bg.convert('RGB'),'card',mid)
    m=ImageOps.mirror(d);m.thumbnail((360,300),Image.LANCZOS);cuts[mid]=save(m,'cut',mid)
print('CARD:'+'{'+','.join(f"{k}:'{v}'" for k,v in sorted(cards.items()))+'}')
print('CUT:'+'{'+','.join(f"{k}:'{v}'" for k,v in sorted(cuts.items()))+'}')
