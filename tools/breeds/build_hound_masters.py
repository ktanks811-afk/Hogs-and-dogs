# Build the Beagle, Redbone Coonhound, Black and Tan Coonhound and American Bully master stacks (m1/m2/m3) from the
# reference pictures, in the same channel layout the coat engine uses for every other body, and write them straight to
# assets/masters/*.webp (lossless, content-hashed). Prints the BODIES lines to paste into index.html.
#   m1 = shading | outline ink | white-spread rank
#   m2 = region id x20 (1 body 2 head 3 muzzle 4 ears 5 eye 6 nose 7 paws 8 tail) | saddle field | tan-point field
#   m3 = alpha | facial-mask field | coat length (0 = short)
# The references are painted on a fake "transparent" checkerboard and face right; they are cut out and mirrored so the
# dog faces left like every other master. Multi-coloured references (the tri Beagle, the Black and Tan, the white-chested
# Bully) have their colour taken out of the shading, colour class by colour class, so the genetics can paint any coat on
# them; their own white, saddle and tan areas become the white-spread, saddle and tan-point fields.
# Run:  python3 tools/breeds/build_hound_masters.py     (pillow, numpy, scipy)
import os,io,re,hashlib,zlib
from PIL import Image,ImageDraw
import numpy as np
from scipy import ndimage as ndi
HERE=os.path.dirname(os.path.abspath(__file__));ROOT=os.path.join(HERE,'..','..');OUT=os.path.join(ROOT,'assets','masters')
html=open(os.path.join(ROOT,'index.html'),encoding='utf-8').read()
W,H=1536,1024
yy,xx=np.mgrid[0:H,0:W]
def ss(a,b,x):t=np.clip((x-a)/(b-a),0,1);return t*t*(3-2*t)
def poly(pts):
    im=Image.new('L',(W,H),0);ImageDraw.Draw(im).polygon(pts,fill=255);return np.array(im)>0
def ell(cx,cy,rx,ry):return ((xx-cx)/rx)**2+((yy-cy)/ry)**2<=1
def rect(x0,y0,x1,y1):return (xx>=x0)&(xx<=x1)&(yy>=y0)&(yy<=y1)
def ref_shading(body):
    m=re.search(body+r":\{w:1536,h:1024,maps:\{m1:'([^']*)',m2:'[^']*',m3:'([^']*)'\}\}",html)
    m1=np.array(Image.open(os.path.join(ROOT,m.group(1))).convert('RGB'));m3=np.array(Image.open(os.path.join(ROOT,m.group(2))).convert('RGB'))
    return np.sort(m1[...,0][m3[...,0]>=128].astype(np.float32))

def cutout(path):
    src=np.array(Image.open(path).convert('RGB').transpose(Image.FLIP_LEFT_RIGHT)).astype(np.float32)
    L=src.mean(2);chroma=src.max(2)-src.min(2);neut=chroma<9
    # the checkerboard: neutral light grey (~214) and white (~253) squares, always both close together; fur never is
    grey=neut&(L>200)&(L<228);white=neut&(L>240)
    gf=ndi.uniform_filter(grey.astype(np.float32),31);wf=ndi.uniform_filter(white.astype(np.float32),31)
    bg=ndi.binary_closing(neut&(L>198)&(gf>.08)&(wf>.08),iterations=2)
    dog=ndi.binary_opening(~bg,iterations=2)
    lab,n=ndi.label(dog);sz=ndi.sum(dog,lab,range(1,n+1));dog=lab==(1+np.argmax(sz))
    dog=ndi.binary_opening(ndi.binary_fill_holes(dog),iterations=1)
    return src,dog

# ---- per-breed layout, in mirrored (facing-left) pixel coordinates ----
HOUND_TAN=lambda c:[ell(*c['brows'][0],14,9),ell(*c['brows'][1],17,10),ell(*c['chest'],60,80)]
CFG={
 'beagle_stack_v1':dict(ref='beagle_reference.png',shade_ref='walker_stack_v1',
   neck=[[530,250],[270,330]],head_y=380,head_x=560,
   muzzle=[(150,130),(250,120),(300,160),(312,240),(300,290),(200,285),(150,250),(140,190)],
   nose=(180,172,36,26),eyes=[(192,103,9,7),(310,110,16,9)],brows=[(205,78),(318,82)],chest=(330,470),
   ears=[[(170,160),(215,190),(218,300),(190,342),(150,342),(138,300),(150,220)],
         [(360,60),(420,55),(490,110),(528,200),(522,290),(470,340),(400,352),(355,320),(350,240),(370,160)]],
   paws=[(205,905,350,995),(505,940,645,1018),(828,880,965,948),(1195,905,1312,990)],
   tail=[[1040,318],[1100,388]],tail_pick=(1180,150),tail_y=400,legs_y=(700,830),
   own_white=True,own_saddle=True,own_tan=False),
 'redbone_stack_v1':dict(ref='redbone_reference.png',shade_ref='walker_stack_v1',
   neck=[[560,275],[315,430]],head_y=440,head_x=590,
   muzzle=[(190,95),(260,85),(302,140),(332,232),(290,248),(230,202),(195,160)],
   nose=(222,118,33,25),eyes=[(245,70,8,7),(340,72,14,9)],brows=[(262,42),(330,45)],chest=(400,520),
   ears=[[(200,190),(252,215),(272,262),(242,332),(210,367),(172,352),(178,270)],
         [(380,70),(440,70),(492,140),(522,230),(502,320),(452,377),(400,372),(378,300),(373,180)]],
   paws=[(222,925,385,995),(475,945,605,1018),(850,900,980,962),(1190,920,1305,992)],
   tail=[[1030,335],[1085,400]],tail_pick=(1260,150),tail_y=410,legs_y=(760,880),
   own_white=False,own_saddle=False,own_tan=False),
 'bnt_stack_v1':dict(ref='black_and_tan_reference.png',shade_ref='walker_stack_v1',
   neck=[[565,280],[315,440]],head_y=450,head_x=595,
   muzzle=[(185,95),(255,85),(302,140),(332,237),(290,252),(225,207),(190,160)],
   nose=(215,118,33,25),eyes=[(240,72,8,7),(338,72,14,9)],brows=[(265,42),(322,44)],chest=(460,540),
   ears=[[(200,215),(262,230),(272,292),(252,362),(210,392),(162,372),(168,290)],
         [(380,70),(440,70),(502,140),(527,230),(512,320),(462,377),(400,372),(378,300),(373,180)]],
   paws=[(225,925,385,995),(475,945,610,1018),(855,900,980,962),(1190,920,1305,992)],
   tail=[[1040,340],[1090,402]],tail_pick=(1290,160),tail_y=415,legs_y=(760,880),
   own_white=False,own_saddle=False,own_tan=True),
 'bully_stack_v1':dict(ref='american_bully_reference.png',shade_ref='apbt_stack_v1',
   neck=[[640,290],[300,395]],head_y=400,head_x=660,
   muzzle=[(190,180),(252,172),(302,210),(312,300),(292,348),(230,352),(195,300),(184,240)],
   nose=(232,212,34,26),eyes=[(222,165,9,8),(352,168,15,10)],brows=[(232,140),(350,142)],chest=(420,540),
   ears=[[(270,52),(292,5),(312,18),(308,72)],
         [(405,52),(420,5),(462,15),(522,72),(547,122),(537,192),(502,162),(462,112)]],
   paws=[(190,905,380,995),(585,915,740,1020),(810,880,965,945),(1180,895,1315,965)],
   tail=[[1092,396],[1108,436]],tail_pick=(1280,590),tail_y=640,legs_y=(800,900),
   # the Bully's tail hangs down over its thigh, so it is outlined by hand rather than cut off at the root
   tail_poly=[(1092,392),(1150,424),(1190,470),(1230,528),(1275,568),(1320,594),(1338,606),(1300,619),(1250,613),(1214,596),(1193,561),(1173,522),(1148,482),(1118,446),(1094,420)],
   own_white=True,own_saddle=False,own_tan=False),
}
RIGS={}
def build(name,c):
    src,A=cutout(os.path.join(HERE,c['ref']))
    L=src.mean(2);chroma=src.max(2)-src.min(2)
    edt=ndi.distance_transform_edt(A);ring=A&(edt<=1.5)
    alpha=ndi.gaussian_filter(A.astype(np.float32),.8);alpha=np.where(A,np.maximum(alpha,.5),alpha)
    # ---- regions ----
    reg=np.ones((H,W),np.uint8)
    (P1,P2)=[np.array(p,np.float32) for p in c['neck']];d=P2-P1;nx,ny=-d[1],d[0]
    side=(xx-P1[0])*nx+(yy-P1[1])*ny;ref=(c['nose'][0]-P1[0])*nx+(c['nose'][1]-P1[1])*ny
    head=(np.sign(side)==np.sign(ref))&(yy<c['head_y'])&(xx<c['head_x'])
    reg[head]=2
    reg[poly(c['muzzle'])&A]=3
    for e in c['ears']:reg[poly(e)&A]=4
    eyes=np.zeros((H,W),bool)
    for e in c['eyes']:eyes|=ell(*e)
    reg[eyes&A]=5
    nz=ell(*c['nose'])&(ndi.gaussian_filter(L,1.5)<95)&A;nz=ndi.binary_fill_holes(ndi.binary_closing(nz,iterations=2))
    reg[nz]=6
    paws=np.zeros((H,W),bool)
    for p in c['paws']:paws|=rect(*p)
    reg[paws&A]=7
    (T1,T2)=[np.array(p,np.float32) for p in c['tail']];d=T2-T1;tnx,tny=-d[1],d[0]
    tside=(xx-T1[0])*tnx+(yy-T1[1])*tny;tref=(c['tail_pick'][0]-T1[0])*tnx+(c['tail_pick'][1]-T1[1])*tny
    cand=A&(np.sign(tside)==np.sign(tref))&(yy<c['tail_y'])&(xx>T1[0]-40)
    lab,n=ndi.label(cand);tl=lab==lab[c['tail_pick'][1],c['tail_pick'][0]]
    if c.get('tail_poly'):tl=poly(c['tail_poly'])&A
    assert tl.sum()>500,(name,'tail pick missed',tl.sum())
    reg[tl]=8
    reg[~A]=0
    # ---- colour classes in the reference: white fur, black/very dark fur, the rest (tan, red, grey) ----
    Ls=ndi.gaussian_filter(L,.7)
    whiteC=A&(Ls>175)&(chroma<60)&~np.isin(reg,[5,6])
    blackC=A&(Ls<62)&~np.isin(reg,[5,6])
    for k in(whiteC,blackC):pass
    whiteC=ndi.binary_opening(whiteC,iterations=2);blackC=ndi.binary_opening(blackC,iterations=2)
    midC=A&~whiteC&~blackC
    # ---- shading: each colour class rank-matched into the reference master's shading range, so the pattern in the
    #      picture doesn't show through as light and dark; the fur texture and the lighting inside each class stay ----
    refv=ref_shading(c['shade_ref'])
    shade=np.zeros((H,W),np.float32)
    for C in(whiteC,blackC,midC):
        if C.sum()<50:continue
        v=Ls[C];o=np.argsort(v);q=np.empty_like(v);q[o]=np.linspace(0,1,len(v))
        shade[C]=np.interp(q,np.linspace(0,1,len(refv)),refv)
    # blend class seams so a colour boundary doesn't leave a step in the light
    seam=ndi.binary_dilation(ndi.morphological_gradient(whiteC.astype(np.uint8)*2+blackC.astype(np.uint8),size=3)>0,iterations=3)&A
    sm=ndi.gaussian_filter(shade*A,3)/(ndi.gaussian_filter(A.astype(np.float32),3)+1e-6)
    shade[seam]=sm[seam]
    eyez=reg==5;shade[eyez]=np.clip(.62+Ls[eyez]/255*1.4,0,1.6)*255/1.6
    nzz=reg==6;shade[nzz]=np.clip(.55+Ls[nzz]/255*2.2,0,1.6)*255/1.6
    shade[ring]=40;shade[~A]=255
    # ---- outline ink: creases from the class-neutral shading, plus a solid outline ----
    sh=ndi.gaussian_filter(shade,.8)
    ink=np.clip((ndi.grey_closing(sh,size=5)-sh-14)/30,0,1)*.5
    ink[reg==6]*=.2;ink[reg==5]*=.45;ink[ring]=1;ink[~A]=0
    ink=np.where(A,np.maximum(ink,np.clip((5.8-edt)/1.6,0,1)),ink)
    # ---- white-spread rank: low = turns white first (toes, chest, muzzle; the picture's own white first) ----
    rng=np.random.default_rng(zlib.crc32(name.encode()))
    def fbm(s,oct=4):
        out=np.zeros((H,W),np.float32);amp=1
        for o in range(oct):
            g=rng.random((int(H/s)+2,int(W/s)+2)).astype(np.float32)
            out+=amp*np.array(Image.fromarray(g).resize((W,H),Image.BICUBIC));s/=2;amp*=.5
        return out
    noise=fbm(180)
    top=np.full(W,H)
    for x in range(W):
        cc=np.nonzero(A[:,x])[0]
        if len(cc):top[x]=cc[0]
    depth=yy-top[None,:]
    rank=.45+.3*(1-ss(0,380,depth))+.2*noise
    rank-=.3*ss(c['legs_y'][0],c['legs_y'][1]+80,yy)
    rank[reg==7]-=.55
    cx,cy=c['chest'];rank-=.6*np.exp(-(((xx-cx)/60)**2+((yy-cy)/90)**2))
    headish=ndi.gaussian_filter(np.isin(reg,[2,3,4,5,6]).astype(np.float32),22)
    rank+=.4*headish+.25*(reg==4)
    if c['own_white']:rank-=.75*ndi.gaussian_filter(whiteC.astype(np.float32),6)
    rank=ndi.gaussian_filter(rank,4)
    wr=np.zeros((H,W),np.float32);v=rank[A];o=np.argsort(v);qq=np.empty_like(v);qq[o]=np.linspace(0,1,len(v));wr[A]=qq*255;wr[~A]=255
    # ---- saddle field: the back and tail (the Beagle's own black saddle where it has one) ----
    tailbase=c['tail'][0][0]
    sad=(1-ss(0,230,depth))*ss(480,640,xx)*(reg==1)
    if c['own_saddle']:sad=np.maximum(sad*.35,ndi.gaussian_filter((blackC&(reg==1)).astype(np.float32),5))
    sad=np.maximum(sad,(reg==8).astype(np.float32)*.9)
    sad=ndi.gaussian_filter(sad.astype(np.float32),5)*A
    # ---- tan points: brows, cheeks and muzzle, chest, lower legs, under the tail (the Black and Tan's own tan) ----
    tan=np.zeros((H,W),np.float32)
    for e in HOUND_TAN(c):tan=np.maximum(tan,e.astype(np.float32))
    tan=np.maximum(tan,((reg==3)&(yy>c['nose'][1]+10)).astype(np.float32))
    tan=np.maximum(tan,(A&(reg!=8)&(reg!=2)&(reg!=4)).astype(np.float32)*ss(c['legs_y'][0]-40,c['legs_y'][1],yy))
    tan=np.maximum(tan,ell(tailbase+30,c['tail'][1][1]-10,22,16).astype(np.float32))
    if c['own_tan']:
        tanC=midC&(chroma>45)&(Ls>60)&~np.isin(reg,[5,6])
        tan=np.maximum(tan*.5,ndi.binary_opening(tanC,iterations=2).astype(np.float32))
    tan=ndi.gaussian_filter(tan,5)*A
    # ---- facial mask: muzzle and flews, fading up past the eyes ----
    mask=ndi.gaussian_filter(((reg==3)|(reg==6)).astype(np.float32),16)
    mask=np.clip(mask*1.7,0,1)*(np.isin(reg,[2,3,5,6]))
    u8=lambda a:np.clip(np.round(a),0,255).astype(np.uint8)
    m1=np.dstack([u8(shade),u8(ink*255),u8(wr)])
    m2=np.dstack([u8(reg*20),u8(sad*255),u8(tan*255)])
    m3=np.dstack([u8(alpha*255),u8(mask*255),np.zeros((H,W),np.uint8)])
    files={}
    for k,a in(('m1',m1),('m2',m2),('m3',m3)):
        b=io.BytesIO();Image.fromarray(a,'RGB').save(b,'WEBP',lossless=True,quality=100,method=6,exact=True);data=b.getvalue()
        assert Image.open(io.BytesIO(data)).convert('RGB').tobytes()==Image.fromarray(a,'RGB').tobytes()
        fn=f"{name}-{k}.{hashlib.sha1(data).hexdigest()[:10]}.webp"
        for old in os.listdir(OUT):
            if old.startswith(name+'-'+k+'.')and old!=fn:os.remove(os.path.join(OUT,old))
        open(os.path.join(OUT,fn),'wb').write(data);files[k]='assets/masters/'+fn
    counts={int(k):int(v) for k,v in zip(*np.unique(reg[A],return_counts=True))}
    print(f"  {name}:{{w:1536,h:1024,maps:{{m1:'{files['m1']}',m2:'{files['m2']}',m3:'{files['m3']}'}}}},")
    print('   regions',counts)
for name,c in CFG.items():build(name,c)
