"""Package all formal task03 outputs and its three task02 inputs; verify after extraction."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZIP_DEFLATED

HERE = Path(__file__).resolve().parent
ROOT = (HERE.parent if (HERE.parent / "task01/reports/panel_definition.json").is_file()
        else HERE if (HERE / "data/derived/task02").is_dir() else HERE.parent)
TARGET = HERE / "deliverables/task03_工作日与休息日比较_完整成果包.zip"


def main():
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    entries = {}
    for path in HERE.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(HERE)
        if any(p in {"data", "deliverables", "__pycache__"} or p.startswith(".backup") for p in rel.parts):
            continue
        if path.name == "figure_contact_sheet.png":
            continue
        entries[rel.as_posix()] = path
    derived = ROOT / "data/derived/task03"
    manifest = json.loads((derived / "derivation_manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["outputs"]) == 10
    for path in derived.iterdir():
        if path.is_file():
            entries["data/derived/task03/" + path.name] = path
    for name in ["daily_panel13.csv", "hourly_panel13.csv", "derivation_manifest.json"]:
        entries["data/derived/task02/" + name] = ROOT / "data/derived/task02" / name
    entries["说明.md"] = HERE / "DELIVERY.md"
    assert all(path.is_file() for path in entries.values())
    with ZipFile(TARGET, "w", compression=ZIP_DEFLATED, compresslevel=9) as z:
        for name, path in sorted(entries.items()):
            if name == "README.md":
                body = path.read_text(encoding="utf-8").replace("(../data/", "(data/").replace("python task03/", "python ")
                z.writestr(name, "本 ZIP 解压后为独立成果包，以下命令在解压根目录运行。\n\n" + body)
            elif name == "data/derived/task03/derivation_manifest.json":
                packaged = json.loads(path.read_text(encoding="utf-8"))
                for record in packaged["inputs"]:
                    if record["path"].startswith("task03/"):
                        record["path"] = record["path"][len("task03/"):]
                packaged["packaging"] = {
                    "layout": "standalone",
                    "source_task01_reference_check": packaged["task01_daily_and_hourly_reference_check"],
                    "note": "Only source paths relocated; formal CSV bytes unchanged. Task01 references are not bundled.",
                }
                packaged["task01_daily_and_hourly_reference_check"] = "not_present_in_standalone_package"
                z.writestr(name, json.dumps(packaged, ensure_ascii=False, indent=2) + "\n")
            else:
                z.write(path, name)
    with ZipFile(TARGET) as z:
        assert z.testzip() is None and len(z.namelist()) == len(entries)
        assert all(not Path(name).is_absolute() and ".." not in Path(name).parts for name in z.namelist())
        assert "reports/task03_report.html" in z.namelist()
    sha = hashlib.sha256(TARGET.read_bytes()).hexdigest()
    TARGET.with_suffix(".zip.sha256").write_text(sha + "  " + TARGET.name + "\n", encoding="utf-8")
    print(f"PASS: {TARGET}; {TARGET.stat().st_size:,} bytes; {len(entries)} files", flush=True)
    print("SHA256 " + sha)
    # 在独立目录中复现，确认压缩包不依赖完整项目的分钟表或 task01。
    with TemporaryDirectory(prefix="task03_verify_", dir=str(TARGET.parent)) as temp:
        temp_root = Path(temp).resolve()
        assert temp_root.parent == TARGET.parent.resolve()
        with ZipFile(TARGET) as z:
            z.extractall(temp_root)
        logs = []
        # Verify the supplied files before regenerating anything, then reproduce.
        for script in ["verify_task03.py", "run_task03.py", "verify_task03.py"]:
            result = subprocess.run([sys.executable, str(temp_root / script)], cwd=str(temp_root),
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            logs.append(result.stdout + result.stderr)
            assert result.returncode == 0, logs[-1]
        for entry in manifest["outputs"]:
            assert hashlib.sha256((temp_root / "data/derived/task03" / Path(entry["path"]).name).read_bytes()).hexdigest() == entry["sha256"], entry["path"]
        logs.append("PASS: standalone reproduction without standard minute tables or task01; all 10 result CSV hashes identical.")
        TARGET.with_suffix(".verification.txt").write_text("\n".join(logs), encoding="utf-8")
    print("PASS: standalone reproduction and all result CSV hashes")


if __name__ == "__main__":
    main()
