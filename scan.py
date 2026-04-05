"""Workflow 1 — scan

Usage:
    python main.py scan <input_folder> [--output-dir <output_dir>]

- Recursively scan input_folder for media files
- Extract original capture date (EXIF > video metadata > file mtime)
- Update each file's mtime to the original capture date
- Write index/<folder_name>.json with stats and per-file info
  (output_dir defaults to <project>/output if not specified)
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

from utils import _now

import exifread
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser

from media_types import classify

SCAN_DIR = Path(__file__).parent / "index"


# ---------------------------------------------------------------------------
# Date extraction
# ---------------------------------------------------------------------------

def _exif_date(path: Path) -> datetime | None:
    """Extract DateTimeOriginal from EXIF (photos)."""
    try:
        with open(path, "rb") as f:
            tags = exifread.process_file(f, stop_tag="EXIF DateTimeOriginal", details=False)
        tag = tags.get("EXIF DateTimeOriginal") or tags.get("Image DateTime")
        if tag:
            return datetime.strptime(str(tag), "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return None


def _hachoir_date(path: Path) -> datetime | None:
    """Extract creation date from video metadata via hachoir."""
    try:
        parser = createParser(str(path))
        if not parser:
            return None
        with parser:
            metadata = extractMetadata(parser)
        if metadata:
            dt = metadata.get("creation_date")
            if dt:
                # hachoir returns a datetime; strip tz so we work in local naive
                if hasattr(dt, "tzinfo") and dt.tzinfo is not None:
                    dt = dt.astimezone().replace(tzinfo=None)
                return dt
    except Exception:
        pass
    return None


def _file_mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime)


def get_capture_date(path: Path, kind: str) -> tuple[datetime, str]:
    """Return (capture_datetime, source) where source is 'exif'|'hachoir'|'mtime'."""
    if kind == "photo":
        dt = _exif_date(path)
        if dt:
            return dt, "exif"
    if kind == "video":
        dt = _hachoir_date(path)
        if dt:
            return dt, "hachoir"
    return _file_mtime(path), "mtime"


# ---------------------------------------------------------------------------
# mtime update
# ---------------------------------------------------------------------------

def set_mtime(path: Path, dt: datetime) -> None:
    """Update file mtime to dt (atime unchanged)."""
    ts = dt.timestamp()
    current_atime = path.stat().st_atime
    os.utime(path, (current_atime, ts))


# ---------------------------------------------------------------------------
# Main scan logic
# ---------------------------------------------------------------------------

def scan(input_folder: str, output_dir: str | None = None) -> None:
    input_path = Path(input_folder).resolve()
    if not input_path.is_dir():
        raise SystemExit(f"Error: '{input_folder}' is not a directory")

    output_path = Path(output_dir).resolve() if output_dir else Path(__file__).parent / "output"

    folder_name = input_path.name
    SCAN_DIR.mkdir(exist_ok=True)
    output_json = SCAN_DIR / f"{folder_name}.json"

    files = []
    counts = {"photo": 0, "video": 0, "unknown": 0, "excluded": 0}

    all_paths = sorted(p for p in input_path.rglob("*") if p.is_file())
    total = len(all_paths)

    print(f"Scanning '{input_path}' ({total} files)...")

    for i, file_path in enumerate(all_paths, 1):
        kind = classify(file_path.name)
        counts[kind] = counts.get(kind, 0) + 1

        if kind == "excluded":
            print(f"  [{i}/{total}] SKIP  {file_path.relative_to(input_path)}")
            continue

        dt, source = get_capture_date(file_path, kind)
        set_mtime(file_path, dt)

        rel = str(file_path.relative_to(input_path))
        size = file_path.stat().st_size
        files.append({
            "path": rel,
            "type": kind,
            "capture_date": dt.isoformat(),
            "date_source": source,
            "size": size,
            "lifecycle": [{"stage": "scanned", "at": _now()}],
        })

        print(f"  [{i}/{total}] {kind.upper():<7} {source:<6}  {rel}")

    result = {
        "input_folder": str(input_path),
        "output_dir": str(output_path),
        "folder_name": folder_name,
        "scanned_at": datetime.now().isoformat(),
        "counts": {
            "total": counts["photo"] + counts["video"] + counts["unknown"],
            "photos": counts["photo"],
            "videos": counts["video"],
            "unknown": counts["unknown"],
            "excluded": counts["excluded"],
        },
        "files": files,
    }

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    c = result["counts"]
    print(
        f"\nDone. {c['total']} files: "
        f"{c['photos']} photos, {c['videos']} videos, {c['unknown']} unknown, "
        f"{c['excluded']} excluded"
    )
    print(f"Saved: {output_json}")
