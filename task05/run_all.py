"""从冻结输入复跑Task05六步及最终核验，任一步失败即停止。"""
import os
import subprocess
import sys
from pathlib import Path


def main():
    here = Path(__file__).resolve().parent
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    for name in ['audit_repository_sources.py', 'reproduce_first_three.py', 'inspect_training.py', 'freeze_rules.py',
                 'audit_rules.py', 'run_task05.py', 'report_task05.py', 'make_manifest.py',
                 'verify_task05.py']:
        print('Running '+name, flush=True)
        subprocess.run([sys.executable, str(here/name)], cwd=here.parent, env=env, check=True)


if __name__ == '__main__':
    main()
