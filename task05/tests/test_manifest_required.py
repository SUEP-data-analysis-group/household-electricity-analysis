"""缺少正式清单必须在读取大数据之前失败，不能静默绕过哈希校验。"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    source=Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='task05-no-manifest-') as temp:
        here=Path(temp)/'task05'
        here.mkdir()
        for name in ['common.py','verify_task05.py']:
            shutil.copy2(source/name,here/name)
        result=subprocess.run([sys.executable,str(here/'verify_task05.py')],capture_output=True,text=True)
        assert result.returncode!=0
        assert 'required_derivation_manifest_exists' in result.stderr
    print('PASS missing manifest is rejected before any source data read')


if __name__=='__main__':
    main()
