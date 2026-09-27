# Build the two pit bull master stacks from the reference images, in the channel layout the coat engine uses for
# every body, and splice them into index.html as data URLs (tools/assets/extract_masters.py then moves them to
# assets/masters/*.webp):
#   pit_bull_terrier_stack_v1                  <- pit_bull_terrier_reference.png   (lean, athletic, running; faces right, flipped)
#   pit_bull_terrier_all_mastiff_mix_stack_v1  <- pit_bull_terrier_all_mastiff_mix_reference.png (heavy, standing; faces left)
#   m1 = shading | outline ink | white-spread rank
#   m2 = region id x20 (1 body 2 head 3 muzzle 4 ears 5 eye 6 nose 7 paws 8 tail 9 tongue/gums 10 teeth) | saddle | tan points
#   m3 = alpha | facial-mask field | coat length (0 = short)
# The coat itself is never painted: shading comes from the photo's light, and every colour comes from the dog's genes.
# Colour markings in a photo (the mix's dark ears and muzzle, its white chest) are treated as colour, not light.
# Run:  python3 tools/pitbull/build_pitbull_masters.py && python3 tools/assets/extract_masters.py   (pillow, numpy, scipy)
import os,re,io,base64
from PIL import Image,ImageDraw
import numpy as np
from scipy import ndimage as ndi
HERE=os.path.dirname(os.path.abspath(__file__));INDEX=os.environ.get('HD_INDEX') or os.path.join(HERE,'..','..','index.html')
html=open(INDEX,encoding='utf-8').read()
W,H=1536,1024
yy,xx=np.mgrid[0:H,0:W]
def poly(pts):
    im=Image.new('L',(W,H),0);ImageDraw.Draw(im).polygon(pts,fill=255);return np.array(im)>0
def ell(cx,cy,rx,ry):return ((xx-cx)/rx)**2+((yy-cy)/ry)**2<=1
def ss(a,b,x):t=np.clip((x-a)/(b-a),0,1);return t*t*(3-2*t)
def side_of(P1,P2,ref):
    d=np.array(P2,float)-np.array(P1,float);nx,ny=-d[1],d[0]
    s=(xx-P1[0])*nx+(yy-P1[1])*ny;r=(ref[0]-P1[0])*nx+(ref[1]-P1[1])*ny;return np.sign(s)==np.sign(r)
def largest(m):
    lab,n=ndi.label(m)
    if n==0:return m
    sz=ndi.sum(m,lab,range(1,n+1));return lab==(1+np.argmax(sz))
rng=np.random.default_rng(11)
def fbm(s,oct=4):
    out=np.zeros((H,W),np.float32);amp=1
    for o in range(oct):
        g=rng.random((int(H/s)+2,int(W/s)+2)).astype(np.float32)
        out+=amp*np.array(Image.fromarray(g).resize((W,H),Image.BICUBIC));s/=2;amp*=.5
    return out
def body_map(body,n):
    m=re.search(body+r":\{w:1536,h:1024,maps:\{m1:'([^']*)',m2:'([^']*)',m3:'([^']*)'\}\}",html);p=m.group(n)
    if p.startswith('data:'):return Image.open(io.BytesIO(base64.b64decode(p.split(',',1)[1])))
    return Image.open(os.path.join(HERE,'..','..',p))
bd1=np.array(body_map('bulldog_stack_v1',1).convert('RGB'));bd3=np.array(body_map('bulldog_stack_v1',3).convert('RGB'))
REF_VALS=np.sort(bd1[...,0][bd3[...,0]>=128].astype(np.float32))

# ---------- the two references, cut out and placed on the 1536x1024 master canvas, facing left ----------
def load_pit():
    a=np.array(Image.open(os.path.join(HERE,'pit_bull_terrier_reference.png')).convert('RGB')).astype(np.float32)[:,::-1]
    # the "transparent" background is a checkerboard baked into the pixels: neutral light gray. The dog is warm tan.
    ch=a.max(2)-a.min(2);L=a.mean(2);dog=(ch>18)|(L<150)
    dog=ndi.binary_opening(dog,iterations=2);dog=largest(dog);dog=ndi.binary_fill_holes(ndi.binary_closing(dog,iterations=4))
    return a,dog
def load_mix():
    m=Image.open(os.path.join(HERE,'pit_bull_terrier_all_mastiff_mix_reference.png')).convert('RGBA')
    s=min(W/m.width,H/m.height);m=m.resize((round(m.width*s),round(m.height*s)),Image.LANCZOS)
    cv=Image.new('RGBA',(W,H),(0,0,0,0));cv.paste(m,((W-m.width)//2,H-m.height));b=np.array(cv).astype(np.float32)
    dog=ndi.binary_erosion(b[...,3]>128,iterations=2)   # trims the red/yellow fringe on the cut-out edge
    dog=ndi.binary_fill_holes(largest(dog));return b[...,:3],dog

def build(name,rgb,A0,cfg):
    L=rgb.mean(2);Ls=ndi.gaussian_filter(L,.6)
    core=ndi.gaussian_filter(A0.astype(np.float32),1.5)>.5;A=ndi.binary_dilation(core,iterations=1)
    ring=A&~ndi.binary_erosion(core,iterations=1)
    alpha=ndi.gaussian_filter(A.astype(np.float32),.8);alpha=np.where(A,np.maximum(alpha,.5),alpha)
    # regions
    reg=np.ones((H,W),np.uint8)
    head=side_of(*cfg['neck'],cfg['head_ref'])&(yy<cfg['head_ymax'])&(xx<cfg['head_xmax'])&A
    reg[head]=2
    reg[poly(cfg['muzzle'])&A]=3
    for e in cfg['ears']:reg[poly(e)&A]=4
    for (cx,cy,rx,ry) in cfg['eyes']:reg[ell(cx,cy,rx,ry)&A]=5
    cx,cy,rx,ry=cfg['nose'];nose=ell(cx,cy,rx,ry)&(Ls<cfg['nose_dark'])&A
    nose=ndi.binary_fill_holes(ndi.binary_closing(nose,iterations=2));reg[nose]=6
    for p in cfg['paws']:reg[poly(p)&A]=7
    tail=A&side_of(*cfg['tail_line'],cfg['tail_ref'])&(yy>cfg['tail_y'][0])&(yy<cfg['tail_y'][1])&(xx>cfg['tail_line'][0][0]-40)
    tail=largest(tail);reg[tail]=8
    mouth=np.zeros((H,W),bool);teeth=np.zeros((H,W),bool)
    if cfg.get('mouth'):
        mp=poly(cfg['mouth'])&A;r,g,b=rgb[...,0],rgb[...,1],rgb[...,2]
        pink=mp&(r-g>38)&(r>110);teeth=mp&(L>185)&((rgb.max(2)-rgb.min(2))<60)
        mouth=ndi.binary_opening(pink,iterations=1)|(mp&(L<60))   # tongue, gums, and the dark of the open mouth
        reg[mouth]=9;reg[teeth]=10
    reg[~A]=0
    # markings in the photo that are colour, not light
    dark_mark=np.zeros((H,W),bool)
    for p in cfg.get('dark_marks',[]):dark_mark|=poly(p)&A&(Ls<cfg.get('dark_mark_L',110))&(reg!=5)&(reg!=6)
    dark_mark=ndi.binary_dilation(ndi.binary_opening(dark_mark,iterations=2),iterations=3)&A&(reg!=5)&(reg!=6)
    blaze=np.zeros((H,W),bool)
    if cfg.get('blaze'):cx,cy,rx,ry=cfg['blaze'];blaze=ndi.binary_dilation(A&(Ls>cfg.get('blaze_L',200))&ell(cx,cy,rx,ry),iterations=3)&A
    fill=dark_mark|blaze|mouth|teeth
    good=(A&~fill).astype(np.float32)
    # lift (or lower) a marking to the light of the coat around it with a smooth gain field, keeping its own detail
    Lf=Ls.copy();fv=ndi.gaussian_filter(Ls*good,18)/(ndi.gaussian_filter(good,18)+1e-6);Lsm=ndi.gaussian_filter(Ls,10)+1e-6
    Lg=ndi.gaussian_filter(Ls,6)
    if cfg.get('dark_marks'):
        area=np.zeros((H,W),bool)
        for p in cfg['dark_marks']:area|=poly(p)
        area=ndi.binary_dilation(area,iterations=6)&A&(reg!=5)&(reg!=6)
        wd=ndi.gaussian_filter((np.clip((150-Lg)/70,0,1)*area).astype(np.float32),5)
        gain=np.clip(ndi.gaussian_filter(fv,6)/Lsm,1,4);Lf=Lf*(1+(gain-1)*wd)
    if cfg.get('blaze'):
        cx,cy,rx,ry=cfg['blaze'];wb=ndi.gaussian_filter((np.clip((Lg-180)/40,0,1)*ell(cx,cy,rx,ry)*A).astype(np.float32),5)
        gain=np.clip(ndi.gaussian_filter(fv,6)/Lsm,.3,1);Lf=Lf*(1+(gain-1)*wb)
    Lf=np.clip(Lf,0,255)
    # shading: the photo's light, half matched to the bulldog master's range, half its own
    v=Lf[A];order=np.argsort(v);q=np.empty_like(v);q[order]=np.linspace(0,1,len(v))
    matched=np.interp(q,np.linspace(0,1,len(REF_VALS)),REF_VALS)
    own=np.clip(Lf[A]/cfg['light_ref']*1.0,0,1.6)*255/1.6
    shade=np.full((H,W),255,np.float32);shade[A]=.45*matched+.55*own
    eyez=reg==5;shade[eyez]=np.clip(.62+Ls[eyez]/255*1.4,0,1.6)*255/1.6
    nz=reg==6;shade[nz]=np.clip(.55+Ls[nz]/255*2.2,0,1.6)*255/1.6
    mz=(reg==9)|(reg==10);shade[mz]=np.clip(.35+Ls[mz]/255*1.05,0,1.6)*255/1.6
    shade[ring]=40;shade[~A]=255
    # outline ink: creases, muscle lines and a solid outline
    ink=np.clip((cfg['ink_dark']-Lf)/22,0,1)*.7
    ink=np.maximum(ink,np.clip((ndi.grey_closing(Lf,size=5)-Lf-cfg['ink_crease'])/30,0,1)*.45)
    ink[reg==6]*=.2;ink[reg==5]*=.45;ink[mz]*=.35;ink[blaze|dark_mark]=0;ink[ring]=1;ink[~A]=0
    edt=ndi.distance_transform_edt(A);ink=np.where(A,np.maximum(ink,np.clip((5.8-edt)/1.6,0,1)),ink)
    # white spread: chest first, then toes, then belly; the head keeps colour longest
    noise=fbm(180);top=np.full(W,H)
    for x in range(W):
        c=np.nonzero(A[:,x])[0]
        if len(c):top[x]=c[0]
    depth=yy-top[None,:]
    rank=.45+.3*(1-ss(0,380,depth))+.2*noise
    rank-=.3*ss(cfg['belly_y'][0],cfg['belly_y'][1],yy)
    rank[reg==7]-=.55
    bx,by,bsx,bsy=cfg['chest'];n2=fbm(60,3)
    rank-=.75*np.exp(-(((xx-bx)/bsx)**2+((yy-by)/bsy)**2))*(.7+.6*n2)            # chest blaze, ragged edge
    rank-=.35*np.exp(-(((xx-bx-30)/(bsx*1.5))**2+((yy-by-110)/(bsy*.9))**2))      # running down the brisket
    headish=ndi.gaussian_filter(np.isin(reg,[2,3,4,5,6,9,10]).astype(np.float32),22)
    rank+=.45*headish+.2*(reg==4)
    rank=ndi.gaussian_filter(rank,4)
    wr=np.full((H,W),255,np.float32);vv=rank[A];o=np.argsort(vv);qq=np.empty_like(vv);qq[o]=np.linspace(0,1,len(vv));wr[A]=qq*255
    # saddle (back and tail) and tan points (brows, cheeks, chest, lower legs, under the tail)
    sad=(1-ss(0,210,depth))*ss(cfg['saddle_x0'],cfg['saddle_x0']+120,xx)*(reg==1)
    sad=np.maximum(sad,(reg==8).astype(np.float32));sad=ndi.gaussian_filter(sad,5)*A
    tan=np.zeros((H,W),np.float32)
    for (cx,cy,rx,ry) in cfg['brows']:tan=np.maximum(tan,ell(cx,cy,rx,ry).astype(np.float32))
    tan=np.maximum(tan,((reg==3)&(yy>cfg['cheek_y'])).astype(np.float32))
    tan=np.maximum(tan,np.clip(ndi.gaussian_filter(ell(bx+10,by+20,bsx*.42,bsy*.5).astype(np.float32),10)*1.8,0,1)*np.clip(.35+1.3*n2,0,1))   # small chest spots with a rough edge
    tan=np.maximum(tan,(yy>cfg['leg_tan_y'])*ss(cfg['leg_tan_y'],cfg['leg_tan_y']+120,yy)*(reg!=8))
    tan=ndi.gaussian_filter(tan,5)*A
    # facial mask: muzzle and flews, fading up the face; on the mix it also covers the ears (its natural mask)
    mask=ndi.gaussian_filter(((reg==3)|(reg==6)).astype(np.float32),16);mask=np.clip(mask*1.7,0,1)*np.isin(reg,[2,3,5,6])
    if cfg.get('mask_ears'):mask=np.maximum(mask,ndi.gaussian_filter((reg==4).astype(np.float32),4)*.9*A)
    def u8(a):return np.clip(np.round(a),0,255).astype(np.uint8)
    if os.environ.get('HD_PREVIEW'):
        pal=np.array([[30,30,30],[140,140,140],[80,170,90],[210,90,90],[90,90,220],[255,255,0],[255,0,255],[0,200,200],[255,150,0],[255,120,160],[255,255,255]],np.uint8)
        pv=os.environ['HD_PREVIEW'];Image.fromarray(pal[reg]).save(pv+name+'_regions.png');Image.fromarray(u8(shade)).save(pv+name+'_shade.png')
        Image.fromarray(u8(255-ink*255)).save(pv+name+'_ink.png');Image.fromarray(u8(wr)).save(pv+name+'_white.png');Image.fromarray(u8(mask*255)).save(pv+name+'_mask.png')
    m1=np.dstack([u8(shade),u8(ink*255),u8(wr)]);m2=np.dstack([u8(reg*20),u8(sad*255),u8(tan*255)]);m3=np.dstack([u8(alpha*255),u8(mask*255),np.zeros((H,W),np.uint8)])
    def png(a):
        b=io.BytesIO();Image.fromarray(a,'RGB').save(b,'PNG',optimize=True);return 'data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()
    new=name+":{w:1536,h:1024,maps:{m1:'"+png(m1)+"',m2:'"+png(m2)+"',m3:'"+png(m3)+"'}}"
    return new,{int(k):int(v) for k,v in zip(*np.unique(reg[A],return_counts=True))}

PIT=dict(neck=[(335,300),(290,650)],head_ref=(150,450),head_ymax=655,head_xmax=345,
  muzzle=[(15,515),(60,488),(110,480),(160,492),(200,520),(265,528),(262,560),(240,610),(200,645),(160,680),(120,690),(100,640),(60,600),(22,572)],
  mouth=[(132,545),(175,530),(236,524),(262,540),(258,582),(232,612),(200,642),(166,672),(146,688),(118,688),(112,640),(122,588)],
  ears=[[(160,352),(172,282),(216,342),(205,358)],[(214,356),(220,285),(282,336),(304,376),(300,402),(278,388)]],
  eyes=[(156,456,14,9)],nose=(44,543,26,20),nose_dark=120,
  paws=[[(55,795),(200,795),(200,895),(55,895)],[(715,860),(860,860),(860,935),(715,935)],[(1010,785),(1140,785),(1140,850),(1010,850)],[(1415,800),(1530,800),(1530,875),(1415,875)]],
  tail_line=[(1130,318),(1180,372)],tail_ref=(1350,230),tail_y=(130,392),
  light_ref=215,ink_dark=95,ink_crease=14,belly_y=(560,640),chest=(420,540,55,70),saddle_x0=560,
  brows=[(150,440,14,8)],cheek_y=560,leg_tan_y=700)
MIX=dict(neck=[(485,30),(330,305)],head_ref=(250,150),head_ymax=320,head_xmax=490,
  muzzle=[(118,140),(160,124),(220,114),(256,140),(282,210),(282,282),(240,298),(196,282),(148,252),(122,210)],
  ears=[[(358,48),(372,28),(440,38),(472,64),(478,92),(460,118),(436,152),(400,168),(368,160),(356,122)]],
  eyes=[(272,110,11,8)],nose=(140,150,24,18),nose_dark=90,
  dark_marks=[[(118,140),(160,124),(220,114),(256,140),(282,210),(282,282),(240,298),(196,282),(148,252),(122,210)],[(358,48),(372,28),(440,38),(472,64),(478,92),(460,118),(436,152),(400,168),(368,160),(356,122)]],dark_mark_L=105,
  blaze=(420,470,60,75),blaze_L=205,mask_ears=True,
  paws=[[(295,905),(445,905),(445,985),(295,985)],[(505,940),(635,940),(635,1015),(505,1015)],[(1085,885),(1205,885),(1205,950),(1085,950)],[(1320,910),(1430,910),(1430,985),(1320,985)]],
  tail_line=[(1165,388),(1228,500)],tail_ref=(1350,540),tail_y=(380,610),
  light_ref=210,ink_dark=80,ink_crease=16,belly_y=(560,650),chest=(425,470,48,75),saddle_x0=640,
  brows=[(270,96,14,8)],cheek_y=220,leg_tan_y=720)

out=[]
a,m=load_pit();out.append(build('pit_bull_terrier_stack_v1',a,m,PIT))
a,m=load_mix();out.append(build('pit_bull_terrier_all_mastiff_mix_stack_v1',a,m,MIX))
for new,info in out:
    name=new.split(':',1)[0];pat=re.escape(name)+r":\{w:1536,h:1024,maps:\{m1:'[^']*',m2:'[^']*',m3:'[^']*'\}\}"
    if re.search(pat,html):html=re.sub(pat,lambda _:new,html)
    else:
        cm=re.search(r"corso_stack_v1:\{w:1536,h:1024,maps:\{m1:'[^']*',m2:'[^']*',m3:'[^']*'\}\}",html);assert cm,'corso_stack_v1 not found'
        html=html[:cm.end()]+",\n  "+new+html[cm.end():]
    print(name,'built; regions',info)
open(INDEX,'w',encoding='utf-8').write(html)
