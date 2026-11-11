"""Fetch official ancillary metadata/files; never execute publisher notebook cells."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/raw/support'
OUT.mkdir(parents=True, exist_ok=True)

def get(url):
    with urlopen(url, timeout=45) as response:
        return response.read()

def save_json(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

url = 'https://api.figshare.com/v2/collections/6742536/articles?page_size=100'
items = json.loads(get(url))
save_json('collection_articles.json', items)
files = []
for item in items:
    meta_url = f"https://api.figshare.com/v2/articles/{item['id']}/versions/1"
    meta = json.loads(get(meta_url))
    save_json(f"article_{item['id']}_v1.json", meta)
    for f in meta['files']:
        if item['id'] == 23686476:
            continue  # Original dataset archive already retained; never replace it.
        filename = Path(f['name']).name
        if filename != f['name']:
            raise ValueError('Unexpected publisher filename')
        data = get(f['download_url'])
        md5 = hashlib.md5(data).hexdigest()
        assert len(data) == f['size'] and md5 == f['computed_md5']
        (OUT / filename).write_bytes(data)
        files.append(dict(article_id=item['id'], version=1, name=filename,
                          url=f['download_url'], size_bytes=len(data), md5=md5,
                          sha256=hashlib.sha256(data).hexdigest(),
                          downloaded_at_utc=datetime.now(timezone.utc).isoformat()))
save_json('support_manifest.json', dict(collection_url=url, files=files,
          collection_note='Article versions pinned to v1; collection listing retrieved at execution time.'))
print(json.dumps(dict(items=[dict(id=i['id'], title=i['title']) for i in items], files=files), ensure_ascii=True))
