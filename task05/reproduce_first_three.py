"""在临时目录复跑原前三步，比较正式结果；不改写冻结来源。"""
import os
import shutil
import subprocess
import sys
import tempfile
import numpy as np
import pandas as pd
from common import *


def main():
    logs = []
    results = []
    with tempfile.TemporaryDirectory(prefix='task05-first-three-') as temp:
        root = Path(temp)
        shutil.copytree(INPUT/'first_three/code', root/'code', ignore=shutil.ignore_patterns('__pycache__'))
        for folder in ['standardized', 'task01', 'task02', 'task04']:
            shutil.copytree(INPUT/folder, root/'inputs'/folder)
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        for script in ['run_A_input_audit.py', 'run_B_contribution.py', 'run_C_peak_contribution.py',
                       'make_delivery_tables.py', 'make_manifest.py', 'verify_package.py']:
            result = subprocess.run([sys.executable, str(root/'code'/script)], cwd=root,
                                    env=env, capture_output=True, text=True, encoding='utf-8')
            logs.append(script+'\n'+result.stdout+result.stderr)
            if result.returncode:
                raise RuntimeError(logs[-1])
        for name in ['contribution_panel13.csv', 'contribution_panel14_supplement.csv',
                     'peak_contribution.csv', 'case_manifest.csv']:
            original = read(INPUT/'first_three/out/交付表'/name)
            rebuilt = read(root/'out/交付表'/name)
            pd.testing.assert_frame_equal(original, rebuilt, check_dtype=False, check_exact=False,
                                          rtol=1e-10, atol=1e-9)
            results.append(dict(file=name, rows=len(original), values_match=True))
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT/'first_three_reproduction.txt').write_text('\n\n'.join(logs), encoding='utf-8')
    write_json(OUT/'first_three_reproduction.json', dict(generated_at=now(), all_pass=True,
               method='original six scripts replayed in an isolated temporary directory',
               numeric_atol=1e-9, numeric_rtol=1e-10, tables=results))
    print('PASS first-three replay: six scripts, four delivery tables match frozen originals')


if __name__ == '__main__':
    main()
