# Run after classify.py: builds the elevation map and encodes both for index.html
# (WORLD_TILES_B64 = row-major run-length pairs (value, run<=255); WORLD_ELEV_B64 = quarter-res uint8 elevation).
import numpy as np,base64;from scipy import ndimage as ndi;from PIL import Image
t=np.load('tiles.npy');H,W=t.shape;rng=np.random.default_rng(11)
def noise(s):
    g=rng.random((int(H/s)+3,int(W/s)+3)).astype(np.float32);return np.array(Image.fromarray(g).resize((W+int(s*2),H+int(s*2)),Image.BICUBIC))[:H,:W]
# rolling hills, rocky high ground, low wet ground
e=.5+.16*(noise(90)-.5)*2+.07*(noise(30)-.5)*2
rock=ndi.gaussian_filter((t==3).astype(np.float32),6);e+=rock*1.6
yy,xx=np.mgrid[0:H,0:W]
for cx,cy,r,h in [(610,20,90,.32),(560,5,60,.2),(625,425,45,.18),(110,220,55,.14),(40,560,50,.1)]:e+=h*np.exp(-((xx-cx)**2+(yy-cy)**2)/(2*r*r))
wet=ndi.gaussian_filter(np.isin(t,[4,8]).astype(np.float32),4);e-=wet*.45
e+=(t==5)*.03
e=ndi.gaussian_filter(e,2.5);e=(e-e.min())/(e.max()-e.min())
q=np.array(Image.fromarray((e*255).astype(np.uint8)).resize((W//4,H//4),Image.BILINEAR))
np.save('elev_q.npy',q)
flat=t.flatten();runs=[];v=flat[0];n=0
for x in flat:
    if x==v and n<255:n+=1
    else:runs+=[int(v),n];v=x;n=1
runs+=[int(v),n]
tb=base64.b64encode(bytes(runs)).decode();eb=base64.b64encode(q.tobytes()).decode()
open('world_tiles.b64','w').write(tb);open('world_elev.b64','w').write(eb)
print('tiles',W,H,'rle KB',round(len(tb)/1024),'elev',q.shape,'KB',round(len(eb)/1024))
