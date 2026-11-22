import numpy as np, sys, os, io, struct
from PIL import Image
OUT=sys.argv[1]
os.makedirs(OUT,exist_ok=True)
L=np.array([-0.74,-0.42,0.5]); L/=np.linalg.norm(L)   # light from upper-left, front

def vnoise(u,v,fu,fv,seed):
    r=np.random.default_rng(seed); g=r.random((fv+2,fu+1)); g[:,-1]=g[:,0]
    x=(u%1.0)*fu; y=np.clip(v,0,0.9999)*fv
    xi=np.floor(x).astype(int); yi=np.floor(y).astype(int); xf=x-xi; yf=y-yi
    sx=xf*xf*(3-2*xf); sy=yf*yf*(3-2*yf)
    a=g[yi,xi]; b=g[yi,xi+1]; c=g[yi+1,xi]; d=g[yi+1,xi+1]
    return (a*(1-sx)+b*sx)*(1-sy)+(c*(1-sx)+d*sx)*sy
def fbm(u,v,fu,fv,oct,seed,gain=.5):
    s=0;a=1;t=0
    for i in range(oct):
        s+=a*vnoise(u,v,fu*2**i,fv*2**i,seed+i); t+=a; a*=gain
    return s/t
def smooth(e0,e1,x):
    t=np.clip((x-e0)/(e1-e0),0,1); return t*t*(3-2*t)
def pal(stops,t):
    t=np.clip(t,0,1); xs=[s[0] for s in stops]; out=np.zeros(t.shape+(3,))
    for k in range(3): out[...,k]=np.interp(t,xs,[s[1][k] for s in stops])
    return out
def hexc(h): return np.array([int(h[i:i+2],16)/255 for i in (1,3,5)])

def sphere(W,H,cx,cy,R,tilt=0.0,incl=0.0):
    ys,xs=np.mgrid[0:H,0:W]+0.5
    X=(xs-cx)/R; Y=(ys-cy)/R; d2=X*X+Y*Y; inside=d2<1
    Z=np.sqrt(np.clip(1-d2,0,1))
    N=np.stack([X,Y,Z],-1)
    # body coords: rotate by tilt (in view plane) and incline toward viewer
    ct,st=np.cos(tilt),np.sin(tilt); bx=ct*X+st*Y; by=-st*X+ct*Y; bz=Z
    ci,si=np.cos(incl),np.sin(incl); by2=ci*by-si*bz; bz2=si*by+ci*bz
    lat=np.arcsin(np.clip(-by2,-1,1)); lon=np.arctan2(bx,bz2)
    alpha=np.clip((1-np.sqrt(d2))*R+0.5,0,1)
    return dict(X=X,Y=Y,Z=Z,N=N,lat=lat,lon=lon,inside=inside,alpha=alpha,d2=d2)

def light(s,albedo,amb=0.03,rim=None,rimw=3.0,spec=None):
    ndl=(s['N']@L)
    diff=smooth(-0.12,0.35,ndl)*np.clip(ndl*0.6+0.55,0,1.2)
    limb=0.55+0.45*s['Z']
    col=albedo*(amb+diff*limb)[...,None]
    if spec is not None:
        Hv=L+np.array([0,0,1.0]); Hv/=np.linalg.norm(Hv)
        sp=np.clip(s['N']@Hv,0,1)**40*spec
        col+=sp[...,None]*0.6
    if rim is not None:
        fr=(1-s['Z'])**rimw*smooth(-0.35,0.4,ndl)
        col+=fr[...,None]*rim
    return col

def save(name,rgb,a,q=72,aq=60):
    rgb=np.clip(rgb,0,1); a=np.clip(a,0,1)
    if a.min()>=1:   # opaque: no alpha channel, nothing to bleed
        p=os.path.join(OUT,name+'.webp'); Image.fromarray((rgb*255).astype(np.uint8),'RGB').save(p,'WEBP',quality=q,method=6)
        return os.path.getsize(p)
    # bleed colour outward under faint/transparent pixels so lossy compression can't smear black into glows
    w=a.copy(); num=rgb*w[...,None]
    for _ in range(10):
        pw=np.pad(w,1,mode='edge'); pn=np.pad(num,((1,1),(1,1),(0,0)),mode='edge')
        w=sum(pw[i:i+w.shape[0],j:j+w.shape[1]] for i in range(3) for j in range(3))/9
        num=sum(pn[i:i+num.shape[0],j:j+num.shape[1]] for i in range(3) for j in range(3))/9
    fill=num/np.maximum(w,1e-6)[...,None]
    k=np.clip(a*2,0,1)[...,None]
    rgb=rgb*k+fill*(1-k)
    im=Image.fromarray(np.dstack([rgb*255,a*255]).astype(np.uint8),'RGBA')
    p=os.path.join(OUT,name+'.webp'); im.save(p,'WEBP',quality=q,method=6,alpha_quality=aq,exact=False)  # bleed above already protects edges
    # Pillow can't ask libwebp for its best alpha compression: re-encode the (already quantised) alpha plane as a
    # max-effort lossless stream and splice it in as the ALPH chunk. Decoded pixels are unchanged.
    d=open(p,'rb').read(); g=np.zeros(a.shape+(3,),np.uint8); g[...,1]=np.asarray(Image.open(p))[...,3]
    b=io.BytesIO(); Image.fromarray(g).save(b,'WEBP',lossless=True,quality=100,method=6); v=b.getvalue()
    new=b'\x11'+v[25:20+struct.unpack('<I',v[16:20])[0]]; i=d.index(b'ALPH'); n=struct.unpack('<I',d[i+4:i+8])[0]
    if len(new)<n:
        d=d[:i+4]+struct.pack('<I',len(new))+new+b'\0'*(len(new)&1)+d[i+8+n+(n&1):]
        open(p,'wb').write(d[:4]+struct.pack('<I',len(d)-8)+d[8:])
    return os.path.getsize(p)

sizes={}
# ---------- ringed planets ----------
# Static ring layers: <name>B (far half, behind the planet) and <name>F (the ring's shadow on the planet plus
# the near half). The planet itself is a spinner drawn between them in the scene.
def rings(name,W,H,R,tilt,incl,r1,r2,stops,gap=.62,seed=77,q=40):
    tilt,incl=np.radians(tilt),np.radians(incl); ct,st=np.cos(tilt),np.sin(tilt); si,ci=np.sin(incl),np.cos(incl)
    Wu,Hu=int(np.ceil(2*r2*R))+4,int(np.ceil(2*max(r2*R*si,R)))+4; cx,cy=Wu/2,Hu/2
    s=sphere(Wu,Hu,cx,cy,R)
    Xr,Yr=s['X'],s['Y']; Zr=Yr*ci/si
    rn=(np.sqrt(Xr**2+(Yr/si)**2)-r1)/(r2-r1)
    _g=np.linspace(0,1,600); _p=np.clip(vnoise(np.zeros(600),_g,1,34,seed)*.45+vnoise(np.zeros(600),_g,1,18,seed+1)*.4+.15*np.sin(_g*38)**2,0,1)
    ring1=np.interp(np.clip(rn,0,1),_g,_p)
    dens=np.where((rn>0)&(rn<1),ring1,0)*smooth(0,.05,rn)*(1-smooth(.95,1,rn))
    dens*=(1-0.92*np.exp(-((rn-gap)/.025)**2))*np.where(rn>gap,.75,1.0); dens=np.clip(dens*0.95,0,.9)
    ringcol=pal(stops,np.clip(rn,0,1)+(ring1-.5)*.25)
    # light in the ring-aligned frame: the planet's shadow on the ring, and the ring's shadow on the planet
    Lr=np.array([ct*L[0]+st*L[1],-st*L[0]+ct*L[1],L[2]])
    P=np.stack([Xr,Yr,Zr],-1); b=P@Lr; disc=b*b-(P*P).sum(-1)+1
    shadow_ring=(disc>0)&((-b+np.sqrt(np.clip(disc,0,None)))>0)
    ring_lit=np.where(shadow_ring,0.12,1.0)*(0.55+0.45*abs(Lr[1]*ci+Lr[2]*si))
    S=np.stack([Xr,Yr,s['Z']],-1); Nr=np.array([0,-ci,si]); tt=-(S@Nr)/(Lr@Nr); Q=S+tt[...,None]*Lr
    rnq=(np.sqrt(Q[...,0]**2+Q[...,1]**2+Q[...,2]**2)-r1)/(r2-r1)
    ringshadow=np.where((tt>0)&(rnq>0)&(rnq<1),0.35+0.65*(1-np.interp(rnq,_g,_p)*0.9),1.0)
    pa=s['alpha']; back=(Zr<0); rcol=ringcol*ring_lit[...,None]
    def cs(k,rgb,al):
        ys,xs=np.where(al>1/255); y0,y1=max(0,ys.min()-1),min(Hu,ys.max()+2); x0,x1=max(0,xs.min()-1),min(Wu,xs.max()+2)
        sizes[k]=save(k,rgb[y0:y1,x0:x1],al[y0:y1,x0:x1],q=q,aq=40)
    cs(name+'B',rcol,dens*back)
    a=(1-ringshadow)*pa; fa=dens*~back; rgb=rcol*fa[...,None]; af=fa+a*(1-fa)
    cs(name+'F',np.where(af[...,None]>1e-4,rgb/np.maximum(af[...,None],1e-4),0),af)
rings('gg',240,138,49,-18,14,1.38,2.32,[(0,hexc('#6f6290')),(.35,hexc('#c9b3dc')),(.6,hexc('#e6d2cc')),(1,hexc('#9fb0d8'))])
rings('sa',220,120,40,12,19,1.24,2.27,[(0,hexc('#6b5a3e')),(.3,hexc('#c8b38a')),(.55,hexc('#e9dcc0')),(.8,hexc('#d4c19a')),(1,hexc('#8f8a7a'))],gap=.58,seed=91)
def gg_surface(u,v):
    lon=(u-.5)*2*np.pi; lat=(v-.5)*np.pi
    warp=fbm(u,v,3,6,5,11)-.5
    bandn=fbm(u*0+.3,v,1,40,4,12)
    band=v*16+warp*0.55+bandn*2.2
    fine=fbm(u+warp*.08,v,6,90,4,21)
    t=(np.sin(band*np.pi)*.5+.5)**1.3*.38+fine*.32+bandn*.3
    a=pal([(0,hexc('#2c1858')),(.3,hexc('#5a3d96')),(.5,hexc('#8f72c2')),(.68,hexc('#bba5dd')),(.85,hexc('#dccbe9')),(1,hexc('#efe0e6'))],t)*0.92
    # storms spread around the globe so the spin reads (longitude offsets wrap)
    for so,sl,su,sv,k,col in ((0.6,-22,.36,.13,.85,'#f3b6d6'),(2.5,14,.26,.09,.8,'#fff1f8'),(-1.9,-6,.24,.08,.8,'#2a1858'),(-.7,28,.18,.07,.75,'#fff1f8')):
        dl=(lon-so+np.pi)%(2*np.pi)-np.pi; dd=(dl/su)**2+((lat-np.radians(sl))/sv)**2
        storm=np.exp(-dd*2.2); swirl=np.sin(np.sqrt(dd)*9-np.arctan2(lat-np.radians(sl),dl*.35)*2)*.5+.5
        a=a*(1-storm[...,None]*k)+(hexc(col)*(.75+.25*swirl[...,None]))*storm[...,None]*k
    return a

# ---------- cratered moon ----------
def craters(u,v,seed,n,depth=.35):
    h=fbm(u,v,5,3,4,61)*.3
    rng=np.random.default_rng(seed)
    for _ in range(n):
        cu,cv,cr=rng.random(),rng.uniform(.15,.85),rng.uniform(.02,.09)
        du=np.minimum(abs(u-cu),1-abs(u-cu))*2*np.cos((v-.5)*np.pi); dv=(v-cv)
        dd=np.sqrt(du**2+dv**2)/cr
        h+=np.where(dd<1,-(1-dd**2)*depth,0)+np.exp(-((dd-1)/.22)**2)*.1
    return h
W=H=40; R=20
s=sphere(W,H,W/2,H/2,R,0,0.2)
u=s['lon']/(2*np.pi)+.5; v=s['lat']/np.pi+.5
h=craters(u,v,5,26)
mare=smooth(.45,.6,fbm(u,v,3,2,3,71))
alb=pal([(0,hexc('#4a4f5c')),(.5,hexc('#9aa1ae')),(1,hexc('#d9dde4'))],.55+h*.6-mare*.25)
gy,gx=np.gradient(h); bump=np.clip(1+(-gx*L[0]*-1-gy*L[1]*-1)*-6,0.5,1.6)
col=light(s,alb*bump[...,None],amb=.02)
sizes['mn']=save('mn',col,np.ones((H,W)),q=78)

# ---------- spiral galaxy ----------
W=H=150; ys,xs=np.mgrid[0:H,0:W]+0.5   # face-on; the scene tilts it (rotate(-28) scale(1,.42)) and spins it
x=(xs-W/2)/(W/2); y=(ys-H/2)/(W/2)
r=np.sqrt(x*x+y*y)+1e-6; th=np.arctan2(y,x)
pitch=np.radians(16)
phase=2*(th-np.log(r)/np.tan(pitch))
arm=(np.cos(phase)*.5+.5)**2.2
clump=fbm(th/(2*np.pi)+.5,np.clip(r,0,1),24,30,4,101)
disk=np.exp(-r/0.22)*(0.25+0.95*arm*(0.6+0.8*clump))
dust=1-0.55*smooth(.75,1,np.cos(phase-0.7)*.5+.5)*smooth(.08,.25,r)
bulge=np.exp(-(r/0.07)**2)*1.6+np.exp(-r/0.05)*.6
dens=disk*dust+bulge
cmix=smooth(0.05,0.45,r)
col=hexc('#fff1d6')*(1-cmix[...,None])+(hexc('#a7b8ff')*.6+hexc('#d8c4ff')*.4)*cmix[...,None]
rng=np.random.default_rng(9); knots=np.zeros_like(r)
for _ in range(60):
    rr=rng.uniform(.1,.45); t0=np.log(rr)/np.tan(pitch)+rng.choice([0,np.pi])+rng.normal(0,.12)
    kx,ky=rr*np.cos(t0),rr*np.sin(t0)
    knots+=np.exp(-(((x-kx)**2+(y-ky)**2)/(.014**2)))*rng.uniform(.4,1)*np.exp(-rr/.3)
col=col*(1-np.clip(knots,0,1)[...,None]*.6)+hexc('#ff9ed8')*np.clip(knots,0,1)[...,None]*.6
lum=np.clip(dens*0.9+knots*0.35,0,None)
a=np.clip(1-np.exp(-lum*1.3),0,1)*smooth(1.0,.7,r); a=np.clip((a-.05)/.95,0,1)  # no faint plateau (compresses into a hard rim)
sizes['sg']=save('sg',np.clip(col,0,1),a,q=50)

# ---------- edge-on galaxy ----------
W,H=220,28; ys,xs=np.mgrid[0:H,0:W]+0.5
x=(xs-W/2)/(W/2); y=(ys-H/2)/(W/2)
disk=np.exp(-abs(x)/0.28)*np.exp(-(y/0.035)**2)
bulge=np.exp(-(x**2+(y*1.6)**2)/0.012)
lane=1-0.8*np.exp(-((y-0.004)/0.008)**2)*smooth(.6,0,abs(x))
tex=0.8+0.4*fbm(x*.5+.5,np.clip(y*4+.5,0,1),20,6,3,111)
lum=(disk*tex*lane*1.2+bulge*1.1)
col=hexc('#ffe9c4')*np.exp(-abs(x)/.25)[...,None]+hexc('#c9c2ff')*(1-np.exp(-abs(x)/.25))[...,None]
a=np.clip(1-np.exp(-lum*1.6),0,1)
sizes['fg']=save('fg',col,a,q=60)

# ---------- nebula (static, low-res, shown large) ----------
W,H=96,60; ys,xs=np.mgrid[0:H,0:W]+0.5; u=xs/W; v=ys/H
w1=fbm(u,v,3,2,5,121)-.5; w2=fbm(u+3,v,3,2,5,131)-.5
n=fbm(u+w1*.5,v+w2*.5,4,3,6,141)
n2=fbm(u+w2*.6+1,v+w1*.4,5,3,6,151)
m1=smooth(.5,.85,n); m2=smooth(.55,.9,n2)
fade=np.exp(-(((u-.45)/.42)**2+((v-.45)/.4)**2))
col=hexc('#9d4edd')*m1[...,None]+hexc('#22d3ee')*m2[...,None]*.8+hexc('#f472b6')*(m1*m2)[...,None]*.6
a=np.clip((m1*.55+m2*.45)*fade,0,1)*.9
sizes['neb']=save('neb',np.clip(col/np.maximum(m1+m2*.8,1e-3)[...,None],0,1),a,q=35)

# ---------- more planet types: one renderer, a few lines each ----------
def lava(u,v):
    rid=1-np.abs(fbm(u,v,5,4,6,251)*2-1); glow=smooth(.86,.97,rid)
    a=pal([(0,hexc('#120c0c')),(1,hexc('#4a3b38'))],fbm(u,v,8,6,4,261))*(1-glow[...,None])
    return a,None,(hexc('#ff6a1a')*glow[...,None]*1.3+hexc('#ffd27a')*(glow**4)[...,None])*smooth(.9,.98,rid)[...,None]*.8
def spin(name,Rpx,surface,q=60):
    W,H=int(round(2*np.pi*Rpx)),int(round(np.pi*Rpx))
    U,V=np.meshgrid((np.arange(W)+.5)/W,1-(np.arange(H)+.5)/H)
    alb,cloud,em=surface(U,V)
    sizes[name+'S']=save(name+'S',alb,np.ones((H,W)),q=q)
    if cloud is not None: sizes[name+'C']=save(name+'C',np.repeat(cloud[...,None],3,-1),np.ones((H,W)),q=30)   # opaque greyscale, screen-blended in the scene
    if em is not None:
        m=em.max(-1); sizes[name+'E']=save(name+'E',em/np.maximum(m,1e-3)[...,None],np.clip(m,0,1),q=q)
def terra2(u,v):
    w=fbm(u,v,4,3,4,201)-.5; n=fbm(u+w*.3,v,5,4,6,211); land=smooth(.49,.53,n)
    ground=pal([(0,hexc('#2f6b3a')),(.5,hexc('#7a8b45')),(1,hexc('#c9a86a'))],fbm(u,v,8,6,4,221))
    sea=pal([(0,hexc('#05214a')),(1,hexc('#1567a8'))],n*1.6)
    cap=smooth(.8,.9,np.abs(v-.5)*2)
    a=sea*(1-land[...,None])+ground*land[...,None]; a=a*(1-cap[...,None])+cap[...,None]*.95
    return a,smooth(.55,.72,fbm(u+w*.5,v,6,10,5,231))*.92,None
spin('pt',26,terra2,q=62)
def jove2(u,v):
    # bands alone look identical while spinning, so add longitude features: wavy edges, patchy belts, storms
    w=fbm(u,v,8,10,4,244)-.5
    t=np.sin((v*11+w*2.2+fbm(u*0,v,1,30,3,242)*1.5)*np.pi)*.5+.5
    a=pal([(0,hexc('#5e3219')),(.35,hexc('#b0703e')),(.65,hexc('#e2c39a')),(1,hexc('#f8eedc'))],t*.75+fbm(u,v,8,60,3,243)*.25)
    a=a*(.8+.4*fbm(u,v,12,16,3,245))[...,None]
    def oval(cu,cv,su,sv,col,k):
        du=(u-cu+.5)%1-.5; e=np.exp(-((du/su)**2+((v-cv)/sv)**2)*2.2)*k
        return e[...,None],col
    for cu,cv,su,sv,col,k in [(.3,.35,.13,.075,'#a8381f',.95),(.3,.35,.07,.04,'#e0703f',.7),
                              (.6,.27,.05,.03,'#fffaf0',1),(.75,.26,.045,.028,'#fffaf0',1),(.9,.28,.05,.03,'#fffaf0',1),
                              (.08,.64,.09,.035,'#3e1f0e',.9),(.48,.72,.06,.026,'#fffaf0',.9)]:
        e,c=oval(cu,cv,su,sv,hexc(col),k); a=a*(1-e)+c*e
    return a
spin('pj',42,lambda u,v:(jove2(u,v),None,None),q=46)
spin('pl',20,lava,q=62)
def venus2(u,v):
    w=fbm(u,v,3,4,5,281)-.5; t=fbm(u*2+w,v+w*.2,4,8,5,291)   # integer u scale keeps the map seamless
    chev=np.abs(((u*3+np.abs(v-.5)*1.6)%1)-.5)*2   # sideways-Y streaks, like Venus in UV
    t=np.clip((t-.5)*2+.5,0,1)*(.75+.25*smooth(.2,.8,chev))
    return pal([(0,hexc('#7a4e1e')),(.45,hexc('#d9ab5e')),(1,hexc('#fdf3d4'))],t)
spin('gg',50,lambda u,v:(gg_surface(u,v),None,None),q=48)
def ocean(u,v):   # the old ice world: deep oceans, polar caps, swirling clouds
    warp=fbm(u,v,4,3,4,31)-.5
    base=pal([(0,hexc('#062a4a')),(.45,hexc('#0b5f99')),(.7,hexc('#2aa7df')),(1,hexc('#9be4ff'))],fbm(u+warp*.2,v,6,4,5,41))
    cap=smooth(.78,.9,np.abs(v-.5)*2)
    a=base*(1-cap[...,None])+hexc('#e8f6ff')*cap[...,None]
    cl=smooth(.48,.7,fbm(u+warp*.35,v+warp*.1,5,10,5,51))[...,None]*.95   # clouds baked in (Earth keeps a drifting layer)
    return a*(1-cl)+hexc('#f2fbff')*cl,None,None
def mars(u,v):
    n=fbm(u,v,6,4,6,81); dark=smooth(.5,.62,fbm(u,v,3,2,4,91))
    a=pal([(0,hexc('#5a1e12')),(.4,hexc('#a8452a')),(.7,hexc('#d9824f')),(1,hexc('#f2c39a'))],n-dark*.3)
    cap=smooth(.84,.92,np.abs(v-.5)*2); return a*(1-cap[...,None])+hexc('#f6efe9')*cap[...,None],None,None
def saturn(u,v):
    w=fbm(u,v,6,8,4,301)-.5
    t=np.sin((v*13+w*.9+fbm(u*0,v,1,26,3,302)*1.4)*np.pi)*.5+.5
    a=pal([(0,hexc('#7a5a30')),(.4,hexc('#c9a86b')),(.75,hexc('#e8d3a2')),(1,hexc('#f7ecd0'))],t*.7+fbm(u,v,10,40,3,303)*.3)
    a=a*(.82+.36*fbm(u,v,12,14,3,304))[...,None]   # patchy belts so the spin reads
    for cu,cv,su,sv,col in ((.2,.68,.13,.05,'#fffaee'),(.55,.36,.16,.05,'#6e4a22'),(.85,.62,.1,.04,'#fffaee'),(.05,.42,.08,.035,'#fffaee')):
        e=np.exp(-((((u-cu+.5)%1-.5)/su)**2+((v-cv)/sv)**2)*2.2)[...,None]*.9; a=a*(1-e)+hexc(col)*e
    return a,None,None
def neptune(u,v):
    w=fbm(u,v,5,6,4,311)-.5
    a=pal([(0,hexc('#16308f')),(.5,hexc('#2f5fe0')),(1,hexc('#6f9cff'))],np.sin((v*7+w*.8)*np.pi)*.25+.5+fbm(u,v,8,20,3,312)*.25)
    e=np.exp(-((((u-.35+.5)%1-.5)/.11)**2+((v-.38)/.055)**2)*2.2)[...,None]*.9; a=a*(1-e)+hexc('#0a1450')*e      # dark spot
    e=np.exp(-((((u-.42+.5)%1-.5)/.05)**2+((v-.33)/.02)**2)*2.2)[...,None]*.9; a=a*(1-e)+hexc('#f2f6ff')*e       # its bright companion cloud
    streak=smooth(.62,.8,fbm(u,v,17,30,3,313))*smooth(.15,.3,np.abs(v-.5))*(1-smooth(.38,.45,np.abs(v-.5)))
    return a*(1-streak[...,None])+streak[...,None]*hexc('#f2f6ff'),None,None
def uranus(u,v):
    a=pal([(0,hexc('#7fd3dc')),(1,hexc('#c6f1ef'))],.45+np.sin(v*9*np.pi)*.08+fbm(u,v,6,12,3,321)*.3)
    cl=np.zeros_like(u)
    for cu,cv in ((.15,.62),(.5,.4),(.8,.66)): cl+=np.exp(-((((u-cu+.5)%1-.5)/.05)**2+((v-cv)/.025)**2)*2.2)
    return a*(1-cl[...,None]*.8)+hexc('#ffffff')*cl[...,None]*.8,None,None
def mercury(u,v):
    h=craters(u,v,13,34,.4)
    a=pal([(0,hexc('#4d4842')),(.5,hexc('#8c857b')),(1,hexc('#cfc8bd'))],.55+h*.7)
    return a,None,None
def pluto(u,v):
    a=pal([(0,hexc('#7a5a3e')),(.5,hexc('#c19a6b')),(1,hexc('#e8d2b0'))],fbm(u,v,6,4,4,331))
    x=((u-.5+.5)%1-.5)/.17; y=(v-.55)/.17
    heart=smooth(.04,-.04,(x*x+y*y-1)**3-x*x*y**3)            # Tombaugh Regio
    du=((u-.2+.5)%1-.5); band=np.exp(-((du/.16)**2+((v-.45)/.07)**2)*2)   # dark Cthulhu region west of it
    a=a*(1-band[...,None]*.85)+hexc('#4a2a1e')*band[...,None]*.85
    return a*(1-heart[...,None])+hexc('#f6efe2')*heart[...,None],None,None
spin('iw',30,ocean)
spin('rp',22,mars,q=66)
spin('sa',40,saturn,q=50)
spin('ne',28,neptune)
spin('pn',30,uranus)
spin('me',14,mercury,q=66)
spin('pu',12,pluto,q=66)
spin('pv',20,lambda u,v:(venus2(u,v),None,None))
# shading overlay for a sphere of radius 50 units: black where unlit, a touch of white on the bright limb
Rs=16; s=sphere(2*Rs,2*Rs,Rs,Rs,Rs); f=light(s,np.ones((2*Rs,2*Rs,3)))[...,0]
dark=np.clip(1-f,0,1); hi=np.clip(f-1,0,1)*.8
sizes['shade']=save('shade',np.repeat((hi>dark)[...,None]*1.0,3,-1),np.maximum(dark,hi),q=70)  # not masked: the scene clips it, and masking left the limb unshaded
# displacement map: orthographic sphere -> equirectangular offsets; the scene's feDisplacementMap scale is 120
n=24; Y,X=(np.mgrid[0:n,0:n]+.5)/n*2-1; r=np.sqrt(X*X+Y*Y); k=np.minimum(1,.999/np.maximum(r,1e-9)); X,Y=X*k,Y*k
lat=np.arcsin(Y); lon=np.arcsin(np.clip(X/np.sqrt(1-Y*Y),-1,1))
dmap=np.dstack([.5+(lon-X)*50/120,.5+(lat-Y)*50/120,np.zeros_like(X)])
Image.fromarray((np.clip(dmap,0,1)*255+.5).astype(np.uint8),'RGB').save(os.path.join(OUT,'dmap.webp'),'WEBP',lossless=True,quality=100,method=6)
sizes['dmap']=os.path.getsize(os.path.join(OUT,'dmap.webp'))
print('textures',sizes,sum(sizes.values()))



# ---------- background sky (separate file: <themesDir>/deep-space.webp, outside the CSS limit) ----------
# ~7000 stars with a power-law brightness spread and colour temperature, soft glows and faint spikes on the
# brightest, and a faint Milky Way band with dust lanes. Transparent, so the theme's nebula colours show through.
W,H=2560,1600; rng=np.random.default_rng(42)
lo=np.zeros((200,320)); yy,xx=np.mgrid[0:200,0:320]/np.array([200,320])[:,None,None]
band=np.exp(-((((yy-.5)-(xx-.5)*-.45)/.16)**2))                       # diagonal band
dust=fbm(xx,yy*.999,8,6,6,401); lanes=smooth(.52,.66,fbm(xx+.3,yy*.999,14,10,5,402))   # v must stay in [0,1)
mw=band*(.55+.6*dust)*(1-.75*lanes*band)
glow=np.asarray(Image.fromarray((np.clip(mw,0,1)*255).astype(np.uint8)).resize((W,H),Image.BICUBIC)).astype(float)/255
img=np.zeros((H,W,3)); alpha=np.zeros((H,W))
mwcol=pal([(0,hexc('#5b4b9a')),(.5,hexc('#7c8fd6')),(1,hexc('#c9d3ff'))],glow)
alpha+=glow*.16; img+=mwcol*(glow*.16)[...,None]
n=7000; bandp=np.asarray(Image.fromarray((band*255).astype(np.uint8)).resize((W,H),Image.BILINEAR)).astype(float)/255
xs=rng.uniform(0,W,n*3); ys=rng.uniform(0,H,n*3)
keep=rng.random(n*3)<(.25+.75*bandp[ys.astype(int),xs.astype(int)]); xs,ys=xs[keep][:n],ys[keep][:n]
mag=rng.pareto(2.2,len(xs))*.22+.16; mag=np.clip(mag,0,1.6)
temp=rng.random(len(xs)); scol=pal([(0,hexc('#a9c7ff')),(.55,hexc('#ffffff')),(.85,hexc('#fff1d6')),(1,hexc('#ffc98a'))],temp)
for dx in (0,1):
    for dy in (0,1):
        xi=np.clip(xs.astype(int)+dx,0,W-1); yi=np.clip(ys.astype(int)+dy,0,H-1)
        w=(1-abs(xs-xs.astype(int)-dx))*(1-abs(ys-ys.astype(int)-dy))*np.minimum(mag,1)
        np.add.at(alpha,(yi,xi),w); np.add.at(img,(yi,xi),scol*w[:,None])
for i in np.argsort(-mag)[:70]:                                         # glows and spikes on the brightest
    cx,cy,m=xs[i],ys[i],mag[i]; r=int(6+m*10); x0,y0=int(cx)-r,int(cy)-r
    if x0<0 or y0<0 or x0+2*r>=W or y0+2*r>=H: continue
    py,px=np.mgrid[0:2*r,0:2*r]+.5; ddx=px-(cx-x0); ddy=py-(cy-y0); d2=ddx*ddx+ddy*ddy
    a=np.exp(-d2/(1.2+m*2))*.9*m+np.exp(-d2/(20+m*30))*.12*m
    a+=(np.exp(-(ddy/.6)**2-np.abs(ddx)/(2.5+m*5))+np.exp(-(ddx/.6)**2-np.abs(ddy)/(2.5+m*5)))*.18*m
    alpha[y0:y0+2*r,x0:x0+2*r]+=a; img[y0:y0+2*r,x0:x0+2*r]+=scol[i]*a[...,None]
a=np.clip(alpha,0,1); rgb=np.clip(img/np.maximum(alpha,1e-6)[...,None],0,1)
Image.fromarray(np.dstack([rgb*255,a*255]).astype(np.uint8),'RGBA').save(os.path.join(OUT,'sky.webp'),'WEBP',quality=86,alpha_quality=90,method=6)
print('sky.webp',os.path.getsize(os.path.join(OUT,'sky.webp')))
