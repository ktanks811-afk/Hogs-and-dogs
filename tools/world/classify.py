# Classify the reference painting into the land system's terrain tiles (2 image px per 5-yd tile).
# Then run encode.py to build the elevation and the strings pasted into index.html as WORLD_TILES_B64 / WORLD_ELEV_B64.
from PIL import Image,ImageDraw;import numpy as np;from scipy import ndimage as ndi
im=np.array(Image.open('ref.png').convert('RGB')).astype(np.float32)
H,W,_=im.shape;r,g,b=im[...,0],im[...,1],im[...,2]
bl=lambda a,s:ndi.gaussian_filter(a,s)
R2,G2,B2=bl(r,2.5),bl(g,2.5),bl(b,2.5);V2=(R2+G2+B2)/3
L=(r+g+b)/3;V1=bl(L,1)
mx=np.maximum(np.maximum(r,g),b);mn=np.minimum(np.minimum(r,g),b);sat=(mx-mn)/(mx+1)
yy,xx=np.mgrid[0:H,0:W]
# swamp region (shallow marsh water rather than open water)
sw=Image.new('L',(W,H),0);ImageDraw.Draw(sw).polygon([(985,215),(1312,215),(1312,690),(1030,690),(990,600),(880,520),(860,420),(930,330)],fill=255);swamp=np.array(sw)>0
PAL={0:(126,150,62),1:(160,130,90),2:(95,70,45),3:(170,170,160),4:(30,60,90),5:(25,70,30),7:(230,200,120),8:(80,100,95),9:(235,215,170)}
CL=dict(GRASS=0,DIRT=1,MUD=2,ROCK=3,WATER=4,TREE=5,TRAIL=7,MARSH=8,SAND=9)
out=np.full((H,W),CL['GRASS'],np.uint8)
bg=B2/(G2+1)
water=(bg>0.8)&(V2<75)
water|=(bg>0.74)&(V2<50)
lab,n=ndi.label(water);sz=ndi.sum(water,lab,range(1,n+1));water=np.isin(lab,1+np.nonzero(sz>350)[0])
forest=(~water)&(V2<78)&(bg<0.8)
out[forest]=CL['TREE']
# mud: dark brown ground (mostly in the swamp)
mud=(~water)&(R2>G2*1.02)&(V2>45)&(V2<95)&(bg<0.7)&swamp
out[mud]=CL['MUD']
out[water]=CL['WATER']
# light grey stone and rapids: rock, unless it is white water next to water
grey=(sat<0.24)&(V1>95)&(~water)
dens=bl(grey.astype(np.float32),5)
rock=(dens>0.2)&(~water)
nearW=ndi.binary_dilation(water,iterations=5)
out[rock&~nearW]=CL['ROCK'];out[(grey|rock)&ndi.binary_dilation(water,iterations=4)&~swamp&(yy>120)]=CL['WATER']   # rapids stay river
# sand: pale beige banks
sand=(V1>135)&(b>r*0.58)&(sat<0.42)&(sat>0.12)&(~rock)
sand&=ndi.binary_dilation(water,iterations=14)
out[sand]=CL['SAND']
# trails: thin strips lighter than their surroundings, tan coloured
th=V1-ndi.median_filter(V1,size=9)
trail=(th>12)&(V1>115)&(r>g)&(g>b)&(sat>0.25)&(~water)&(~sand)
trail=ndi.binary_opening(trail,structure=np.ones((1,1)))
lab,n=ndi.label(trail,structure=np.ones((3,3)));sz=ndi.sum(trail,lab,range(1,n+1));trail=np.isin(lab,1+np.nonzero(sz>25)[0])
out[trail]=CL['TRAIL']
out[water&swamp&(V2>38)]=CL['MARSH']
np.save('class_px.npy',out)
# game grid: 2 px per tile, majority vote, then a light mode filter (trails kept thin)
TW,TH=W//2,H//2;o2=out[:TH*2,:TW*2].reshape(TH,2,TW,2).transpose(0,2,1,3).reshape(TH,TW,4)
cnt=np.stack([(o2==k).sum(-1) for k in range(10)],-1);tile=cnt.argmax(-1).astype(np.uint8)
tile[(o2==7).sum(-1)>=1]=7
sm=np.stack([ndi.uniform_filter((tile==k).astype(np.float32),3) for k in range(10)],-1);mode=sm.argmax(-1).astype(np.uint8)
keep=(tile==7)|(tile==4)&(sm[...,4]>.3);tile=np.where(keep,tile,mode)
# bridge small trail gaps (not across water)
tr=ndi.binary_closing(tile==7,structure=np.ones((3,3)),iterations=1)&np.isin(tile,[0,1,2,5,7])
tile[tr]=7
np.save('tiles.npy',tile)
rgb2=np.zeros((TH,TW,3),np.uint8)
for k,c in PAL.items():rgb2[tile==k]=c
Image.fromarray(np.hstack([np.array(Image.open('ref.png').convert('RGB').resize((TW,TH))),rgb2])).save('compare_tiles.png')
v2,c2=np.unique(tile,return_counts=True);print('tiles',TW,TH,{int(v):round(c/tile.size*100,1) for v,c in zip(v2,c2)})
rgb=np.zeros((H,W,3),np.uint8)
for k,c in PAL.items():rgb[out==k]=c
Image.fromarray(rgb).save('class_px.png')
vals,cnt=np.unique(out,return_counts=True);print({int(v):round(c/out.size*100,1) for v,c in zip(vals,cnt)})
