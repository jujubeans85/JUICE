#!/usr/bin/env python3
"""Build offline music-list exports from the one canonical catalogue."""
import argparse, base64, hashlib, html, json, re
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

VIDEO_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')

def video_id(track):
    value = track.get('youtube_id')
    if value:
        if not VIDEO_ID.fullmatch(value):
            raise ValueError('Invalid YouTube video ID')
        return value
    url = urlsplit(track.get('url', ''))
    host = (url.hostname or '').lower()
    value = url.path.strip('/') if host == 'youtu.be' else parse_qs(url.query).get('v', [''])[0] if host in {'www.youtube.com', 'youtube.com', 'm.youtube.com', 'music.youtube.com'} else ''
    return value if VIDEO_ID.fullmatch(value) else None

def validate(data):
    ids = set()
    for item in data:
        if item['id'] in ids: raise ValueError('Duplicate catalogue ID: '+item['id'])
        ids.add(item['id'])
        if urlsplit(item.get('url', '')).scheme not in {'http','https'}: raise ValueError('Invalid source URL')
        tracks = item.get('tracks', [])
        if tracks and [t['position'] for t in tracks] != list(range(1,len(tracks)+1)): raise ValueError('Track order must be contiguous')
        for track in tracks:
            for key in ['artist','title','version','url']:
                if not track.get(key): raise ValueError('Track missing '+key)
            video_id(track)

def replay_links(item):
    tracks=item.get('tracks',[])
    vids=[video_id(t) for t in tracks]
    if not tracks or not all(vids): return []
    # Split long queues conservatively; retain all IDs in their original order.
    return ['https://www.youtube.com/watch_videos?video_ids='+','.join(vids[i:i+50]) for i in range(0,len(vids),50)]

def build(root):
    data=json.loads((root/'catalogue.json').read_text());validate(data)
    (root/'covers').mkdir(exist_ok=True)
    for d in data:
        if not (root/d['image']).exists():
            title=html.escape(d['title']);symbol=html.escape(d.get('symbol','CJ'))
            (root/d['image']).write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400"><rect width="400" height="400" fill="{d.get("color","#e9d56d")}"/><text x="26" y="45" font-family="Arial" font-size="16">CRATE JUICE / {d["id"]}</text><text x="24" y="260" font-family="Arial" font-weight="bold" font-size="180">{symbol}</text><text x="26" y="350" font-family="Arial" font-size="20">SMOKE, GRAVEL &amp; GRACE</text></svg>')
    app=(root/'app.js').read_text();css=(root/'style.css').read_text();template=(root/'template.html').read_text()
    online=template.replace('<!--STYLE-->','<link rel="stylesheet" href="style.css">').replace('<!--SCRIPT-->','<script src="app.js"></script>')
    (root/'index.html').write_text(online)
    offline=json.loads(json.dumps(data))
    for d in offline:
        d['image']='data:image/svg+xml;base64,'+base64.b64encode((root/d['image']).read_bytes()).decode()
    safe_json=json.dumps(offline,ensure_ascii=False).replace('<','\\u003c')
    standalone=template.replace('<link rel="manifest" href="manifest.webmanifest">','')
    offline_html=standalone.replace('<!--STYLE-->','<style>'+css+'</style>').replace('<!--SCRIPT-->','<script>window.CJ_OFFLINE='+safe_json+';</script><script>'+app+'</script>')
    (root/'offline.html').write_text(offline_html)
    text=['CRATE JUICE — MUSIC LIST INDEX','Offline tracklists and source links. Streaming needs internet.','']
    for d in data:
        text.extend([d['id']+' — '+d['title'],d.get('url',''),'Tracklist: '+d.get('tracklist_status','index-only')])
        for i,link in enumerate(replay_links(d),1):text.append('Fresh YouTube queue '+str(i)+': '+link)
        for t in d.get('tracks',[]):text.extend([f"{t['position']:02}. {'* ' if t.get('seed') else ''}{t['artist']} — {t['title']} [{t['version']}] {t.get('duration','')}",t['url']])
        text.append('')
    (root/'music-index.txt').write_text('\n'.join(text))
    revision=hashlib.sha256((root/'catalogue.json').read_bytes()+app.encode()+css.encode()+template.encode()).hexdigest()[:16]
    (root/'revision.json').write_text(json.dumps({'revision':revision,'entries':len(data),'complete_tracklists':sum(d.get('tracklist_status')=='complete' for d in data)})+'\n')
    sw=(root/'sw.template.js').read_text().replace('__REVISION__',revision)
    (root/'sw.js').write_text(sw)
    print(json.dumps({'revision':revision,'entries':len(data),'complete_tracklists':sum(bool(d.get('tracks')) for d in data),'offline_bytes':(root/'offline.html').stat().st_size}))

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).parent);p.add_argument('--upsert',type=Path);p.add_argument('--check',action='store_true');args=p.parse_args()
    root=args.root.resolve()
    if args.upsert:
        incoming=json.loads(args.upsert.read_text());data=json.loads((root/'catalogue.json').read_text());old=next((d for d in data if d['id']==incoming['id']),None)
        if old: old.update(incoming)
        else: data.insert(0,incoming)
        validate(data);temp=root/'catalogue.json.tmp';temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');temp.replace(root/'catalogue.json')
    if args.check: validate(json.loads((root/'catalogue.json').read_text()));print('Catalogue valid')
    else: build(root)

if __name__=='__main__':main()
