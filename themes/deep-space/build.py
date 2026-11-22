"""Build the Deep Space T3 Code theme.

Sources (all in this folder):
  theme.css   readable CSS. url("svg:NAME") inlines NAME.svg, tex:NAME inlines a texture.
  *.svg       star fields and the animated scene (may reference tex:NAME).
  textures.py procedural planet/galaxy textures, rendered to WebP.
  meta.json   theme name and colour roles.

usage: python3 -I build.py <out.json>     (needs numpy + Pillow)
"""
import base64,glob,json,os,re,subprocess,sys,tempfile,hashlib
HERE=os.path.dirname(os.path.abspath(__file__))
src=lambda n:open(os.path.join(HERE,n)).read()
SPIN=("<pattern id='{0}' href='#P'>"
      "<image href='tex:{0}' preserveAspectRatio='none'/>"
      "<animateTransform attributeName='patternTransform' from='{1}' to='{2}' dur='{3}' repeatDur='indefinite'/></pattern>")
def spin(m):   # <spin id='X' dur='N' [rev]/>: X's surface map scrolling once around the planet every N seconds
    return SPIN.format(m.group(1),*(('0','-314.16') if m.group(3) else ('-314.16','0')),m.group(2))
def scene_src():   # pop*.svg (optional): extra visitors spliced in just before </svg>
    s=src('scene.svg'); extra=''.join(open(p).read() for p in sorted(glob.glob(os.path.join(HERE,'pop*.svg'))))
    return re.sub(r"<spin id='(\w+)' dur='(\d+)'( rev)?/>",spin,s.replace('</svg>',extra+'</svg>'))
_tmp=tempfile.TemporaryDirectory(); tmp=_tmp.name   # removed when the build exits
subprocess.run([sys.executable,'-I',os.path.join(HERE,'textures.py'),tmp],check=True,stdout=subprocess.DEVNULL)
tex=lambda s:re.sub(r'tex:(\w+)',lambda m:'data:;base64,'+base64.b64encode(open(os.path.join(tmp,m.group(1)+'.webp'),'rb').read()).decode(),s)
enc=lambda s:s.replace('%','%25').replace('#','%23').replace('</style','%3C/style')   # raw < > are fine in a quoted data: URL; '</style' would end an HTML <style> that embeds this CSS
NAMES=[a+b for a in ['']+list('abcdefghijklmnopqrstuvwxyz') for b in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ']
def tighten(s):   # output-only: one/two-letter ids (most used first) and no space before negative path numbers
    s=re.sub(r"\b(d|path)='([^']*)'",lambda m:m.group(1)+"='"+m.group(2).replace(' -','-')+"'",s)
    ids=re.findall(r"\bid='([\w-]+)'",s)
    uses=lambda i:len(re.findall(r"(?:url\(#|href='#)"+re.escape(i)+r"[)']",s))
    for i,new in zip(sorted(ids,key=uses,reverse=True),NAMES):
        s=re.sub(r"(\bid='|url\(#|href='#)"+re.escape(i)+r"(?=[)'])",lambda m:m.group(1)+new,s)
    return s
# SVGs: drop comments and collapse whitespace. A raw newline inside a CSS string invalidates the whole declaration.
svg=lambda n:enc(tex(tighten(re.sub(r'>\s+<','><',re.sub(r'\s+',' ',re.sub(r'<!--.*?-->','',scene_src() if n=='scene' else src(n+'.svg'),flags=re.S)).strip()))))
c=re.sub(r'url\("svg:(\w+)"\)',lambda m:'url("data:image/svg+xml,'+svg(m.group(1))+'")',src('theme.css'))
# minify everything outside url(...)
urls=[]
c=re.sub(r'url\("[^"]*"\)',lambda m:urls.append(m.group(0)) or f'\0{len(urls)-1}\0',c)
c=re.sub(r'/\*.*?\*/','',c,flags=re.S); c=re.sub(r'\s+',' ',c)
c=re.sub(r' ?([{};,>]) ?',r'\1',c).replace(';}','}')
# output-only CSS shortening: #0000 for transparent, unquoted simple attribute values, short private names
c=re.sub(r'\btransparent\b','#0000',c)
c=re.sub(r'\[([\w-]+)([~^$*|]?)="([A-Za-z_][\w-]*)"\]',r'[\1\2=\3]',c)
for i,v in enumerate(sorted(set(re.findall(r'--ds-[\w-]+',c)),key=lambda v:(-c.count(v),v))): c=re.sub(re.escape(v)+r'(?![\w-])','--_'+NAMES[i],c)   # ties broken by name: reproducible
for i,k in enumerate(sorted(set(re.findall(r'\bds-[a-z]+\b',c)))): c=re.sub(r'\b'+k+r'\b','_'+NAMES[i],c)
c=re.sub(r'\0(\d+)\0',lambda m:tex(urls[int(m.group(1))]),c).strip()
assert '\\' not in c and len(c)<100000,len(c)
assert not re.search(r'url\("[^"]*[\n\r\f]',c),'newline inside a url string'
theme=json.loads(src('meta.json')); theme['css']=c
os.makedirs(os.path.dirname(os.path.abspath(sys.argv[1])),exist_ok=True); json.dump(theme,open(sys.argv[1],'w'),indent=2,ensure_ascii=False); open(sys.argv[1],'a').write('\n')
# the background sky ships beside the theme as <themeId>.webp; T3 exposes it as var(--theme-background-image)
import shutil; shutil.copy(os.path.join(tmp,'sky.webp'),os.path.join(os.path.dirname(os.path.abspath(sys.argv[1])),'deep-space.webp'))
print(len(c),hashlib.sha256(c.encode()).hexdigest())
