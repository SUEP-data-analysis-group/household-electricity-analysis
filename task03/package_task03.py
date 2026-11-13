"""将 task03 及必要 task02 输入打包；不包含原始大表和其他成员成果。"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "deliverables/task03_工作日与休息日比较_成果包.zip"


def main():
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    files = []
    for folder in [ROOT / "task03", ROOT / "data/derived/task03"]:
        files.extend(p for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.name != "figure_contact_sheet.png")
    files += [ROOT / "data/derived/task02" / n for n in ["daily_panel13.csv", "hourly_panel13.csv", "derivation_manifest.json"]]
    with ZipFile(TARGET, "w", compression=ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(files):
            z.write(path, path.relative_to(ROOT).as_posix())
        z.write(ROOT / "task03/DELIVERY.md", "说明.md")
    with ZipFile(TARGET) as z:
        assert z.testzip() is None
        assert len(z.namelist()) == len(set(z.namelist()))
        assert "task03/reports/task03_report.html" in z.namelist()
    sha = hashlib.sha256(TARGET.read_bytes()).hexdigest()
    TARGET.with_suffix(".zip.sha256").write_text(sha + "  " + TARGET.name + "\n", encoding="utf-8")
    print(f"PASS: {TARGET}; {TARGET.stat().st_size:,} bytes; {len(files)+1} files")
    print("SHA256 " + sha)
    # 在独立目录中复现，确认压缩包不依赖完整项目的分钟表或 task01。
    with TemporaryDirectory(prefix="task03_verify_", dir=str(TARGET.parent)) as temp:
        temp_root = Path(temp).resolve()
        assert temp_root.parent == TARGET.parent.resolve()
        with ZipFile(TARGET) as z:
            z.extractall(temp_root)
        logs = []
        for script in ["run_task03.py", "verify_task03.py"]:
            result = subprocess.run([sys.executable, str(temp_root / "task03" / script)], cwd=str(temp_root),
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            logs.append(result.stdout + result.stderr)
            assert result.returncode == 0, logs[-1]
        manifest = json.loads((ROOT / "data/derived/task03/derivation_manifest.json").read_text(encoding="utf-8"))
        for entry in manifest["outputs"]:
            assert hashlib.sha256((temp_root / entry["path"]).read_bytes()).hexdigest() == entry["sha256"], entry["path"]
        logs.append("PASS: standalone reproduction without standard minute tables or task01; all 10 result CSV hashes identical.")
        TARGET.with_suffix(".verification.txt").write_text("\n".join(logs), encoding="utf-8")
    print("PASS: standalone reproduction and all result CSV hashes")


if __name__ == "__main__":
    main()
