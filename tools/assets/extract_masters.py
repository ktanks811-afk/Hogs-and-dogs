# Move the master picture maps (dog body stacks in Coat BODIES, horse masters in HORSE_MASTERS) out of index.html
# into assets/masters/*.webp. Lossless WebP keeps every pixel value exact; the file name carries a content hash so
# the files can be cached forever (see vercel.json). Safe to run again after a tool splices a new master in as a
# data URL: only data URLs are moved, and unchanged maps land on the same file name.
# Run:  python3 tools/assets/extract_masters.py    (pillow)
import os,re,io,base64,hashlib
from PIL import Image
ROOT=os.path.abspath(os.path.join(os.path.dirname(__file__),'..','..'))
P=os.path.join(ROOT,'index.html');OUT=os.path.join(ROOT,'assets','masters');os.makedirs(OUT,exist_ok=True)
s=open(P).read()
# a map is  m1:'data:...'  (dog bodies) or  "m1":"data:..."  (horse masters); the owner key is the nearest name before it
pat=re.compile(r"""(["']?)(m[123])\1:(["'])data:image/png;base64,([A-Za-z0-9+/=]+)\3""")
owner=re.compile(r"""(?:^|[{,\s])["']?([A-Za-z_][\w]*)["']?:\{["']?w["']?:\d+""")
out=[];last=0;moved=0;saved=0;key='master'
for m in pat.finditer(s):
    if m.group(2)=='m1':names=owner.findall(s,max(0,m.start()-3000),m.start());key=names[-1] if names else 'master'
    raw=base64.b64decode(m.group(4));im=Image.open(io.BytesIO(raw));b=io.BytesIO()
    im.save(b,'WEBP',lossless=True,quality=100,method=6,exact=True);data=b.getvalue()
    # never trust the encoder blindly: the decoded pixels must match the original exactly
    assert Image.open(io.BytesIO(data)).convert(im.mode).tobytes()==im.tobytes(),key
    fn=f"{key}-{m.group(2)}.{hashlib.sha1(data).hexdigest()[:10]}.webp";open(os.path.join(OUT,fn),'wb').write(data)
    q=m.group(1);out.append(s[last:m.start()]+f"{q}{m.group(2)}{q}:{m.group(3)}assets/masters/{fn}{m.group(3)}");last=m.end();moved+=1;saved+=len(m.group(0))
out.append(s[last:]);s=''.join(out);open(P,'w').write(s)
print(f'moved {moved} maps, index.html shrank by {saved/1e6:.1f} MB to {len(s)/1e6:.2f} MB')
