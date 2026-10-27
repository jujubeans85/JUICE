#!/usr/bin/env python3
"""Regenerate SVG covers from catalogue.json, the canonical catalogue."""
from pathlib import Path
import html,json
BG='#141A19'
INK='#17201E'
def esc(x): return html.escape(str(x), quote=True)

def text(x,y,s,size=48,color=INK,weight=400,anchor='start',font='Nimbus Sans, Arial, sans-serif',spacing=0):
    return f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" fill="{color}" letter-spacing="{spacing}">{esc(s)}</text>'

def tile_body(d):
    proposed = d['status']=='PROPOSED'
    color=d['color']; fg=color if proposed else INK; bg=BG if proposed else color
    v=[f'<rect width="1600" height="1600" fill="{bg}"/>']
    # Repeated geometric ornament is deliberately subordinate to the identifiers.
    v += [f'<circle cx="1460" cy="580" r="520" fill="none" stroke="{fg}" stroke-width="2" opacity=".14"/>',
          f'<circle cx="1460" cy="580" r="445" fill="none" stroke="{fg}" stroke-width="2" opacity=".11"/>',
          f'<path d="M1050 235H1492V677" fill="none" stroke="{fg}" stroke-width="2" opacity=".16"/>',
          f'<rect x="35" y="35" width="1530" height="1530" fill="none" stroke="{fg}" stroke-width="3" opacity=".45"/>']
    v.append(text(105,155,d['id'],58,fg,400,font='DejaVu Sans Mono, monospace'))
    v.append(text(1490,155,'PROPOSED' if proposed else 'CRATE JUICE',47,fg,700,'end',spacing=2))
    v.append(text(88,806,d['symbol'],680,fg,700,spacing=-24))
    if d['edition']:
        v.append(text(105,1010,d['edition'],220,fg,700,spacing=-6))
        v.append(text(1485,998,'EDITION',39,fg,700,'end',spacing=4))
    else:
        v.append(text(107,992,d['family'],47,fg,700,spacing=4))
    v.append(f'<path d="M105 1070H1495" stroke="{fg}" stroke-width="3" opacity=".5"/>')
    for i,s in enumerate(d['lines']):
        # Fit long labels once at source, keeping a consistent type scale.
        size=min(90, 1370/max(len(s)*.52,1))
        v.append(text(105,1191+i*111,s,round(size,1),fg,700,spacing=-1))
    v.append(text(105,1483,d['family'] if d['edition'] else 'CRATE JUICE',40,fg,700,spacing=4))
    for i in range(7):
        selected=i==ord(d['position'][0])-65
        v.append(f'<rect x="{1235+i*39}" y="1444" width="23" height="38" fill="{fg}" opacity="{1 if selected else .18}"/>')
    clip='clip-'+d['id']
    return f'<defs><clipPath id="{clip}"><rect width="1600" height="1600"/></clipPath></defs><g clip-path="url(#{clip})">'+''.join(v)+'</g>'

def svg_doc(body,w=1600,h=1600):
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">{body}</svg>'

def main():
 root=Path(__file__).resolve().parent
 data=json.loads((root/'catalogue.json').read_text())
 for d in data:
  dest=root/d['image'];dest.parent.mkdir(parents=True,exist_ok=True)
  dest.write_text(svg_doc(tile_body(d)))
 print(f'Rebuilt {len(data)} covers')
if __name__=='__main__':main()
