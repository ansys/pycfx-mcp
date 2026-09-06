#!/usr/bin/env python3
"""Build AiConnect .acpkg archive and SHA256 checksum for ansys-cfx-mcp."""

import hashlib
import json
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
dist = root / "dist"
dist.mkdir(exist_ok=True)

with open(root / "manifest.json", encoding="utf-8") as f:
    manifest = json.load(f)

cid = manifest["id"]
ver = manifest["version"]
os_name = manifest["platform"]["os"]
arch = manifest["platform"]["arch"]

pkg_filename = f"{cid}-{ver}-{os_name}-{arch}.acpkg"
out_pkg = dist / pkg_filename

files = [
    "manifest.json",
    "marketplace.json",
    "TUTORIAL.md",
    "run_server.py",
    "LICENSE",
]
dirs = ["assets", "src", "_vendor"]

print(f"Packing {pkg_filename}...")
with zipfile.ZipFile(out_pkg, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
    for f in files:
        fp = root / f
        if fp.is_file():
            zf.write(fp, f)
    for d in dirs:
        dp = root / d
        if dp.is_dir():
            for p in dp.rglob("*"):
                if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
                    zf.write(p, p.relative_to(root).as_posix())

sha256 = hashlib.sha256(out_pkg.read_bytes()).hexdigest()
checksum_file = dist / f"{out_pkg.name}.sha256"
checksum_file.write_text(f"{sha256} *{out_pkg.name}\n", encoding="ascii")

print(f"Built {out_pkg.name} ({out_pkg.stat().st_size:,} bytes)")
print(f"SHA256: {sha256}")
