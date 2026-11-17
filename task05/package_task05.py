"""只打包Task05自包含成果；测试ZIP CRC并保存SHA-256。"""
import hashlib
import json
import zipfile
from common import *


def main():
    verification=json.loads((OUT/'verification_task05.json').read_text(encoding='utf-8'))
    assert verification['all_pass'],'Run verify_task05.py before packaging'
    manifest=json.loads((OUT/'derivation_manifest.json').read_text(encoding='utf-8'))
    for f in manifest['files']: assert sha(ROOT/f['path'])==f['sha256'],f['path']
    dest=ROOT/'deliverables';dest.mkdir(exist_ok=True)
    package=dest/'task05_完整成果包_v1.0.1_20261117.zip'
    with zipfile.ZipFile(package,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for base in [HERE,OUT]:
            for path in sorted(base.rglob('*')):
                if path.is_file() and '__pycache__' not in path.parts and path.suffix!='.pyc':
                    z.write(path,path.relative_to(ROOT).as_posix())
        z.write(HERE/'DELIVERY.md','开始阅读.md')
    with zipfile.ZipFile(package) as z:
        assert z.testzip() is None
        count=len(z.infolist())
    digest=sha(package)
    (dest/'task05_完整成果包_v1.0.1_20261117.sha256').write_text(digest+'  '+package.name+'\n',encoding='utf-8')
    print('PASS ZIP CRC;',count,'files;',package.stat().st_size,'bytes; SHA256',digest)


if __name__=='__main__': main()
