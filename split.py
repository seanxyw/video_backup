"""Workflow 2 — split

Usage:
    python main.py split <input_folder>

- Read scan/<folder_name>.json (must run `scan` first)
- Copy photos  → output/photos/<original_subfolder_structure>/
- Copy videos  → output/youtube/<subfolder>_<filename>  (flat)
- Copy unknowns→ output/unknown/<original_subfolder_structure>/
- Verify each copied file's size matches the scan record
"""

import json
import shutil
from pathlib import Path

from utils import _now

BASE_DIR = Path(__file__).parent
SCAN_DIR = BASE_DIR / "index"
OUTPUT_DIR = BASE_DIR / "output"


def split(folder_name: str) -> None:
    scan_json = SCAN_DIR / f"{folder_name}.json"
    if not scan_json.exists():
        raise SystemExit(
            f"Error: index file not found: {scan_json}\n"
            f"Run 'python main.py scan <input_folder>' first."
        )

    with open(scan_json, encoding="utf-8") as f:
        data = json.load(f)

    input_path = Path(data["input_folder"])
    if not input_path.is_dir():
        raise SystemExit(f"Error: input folder '{input_path}' not found (stored in index)")

    files = data["files"]
    index_by_path = {e["path"]: e for e in files}
    total = len(files)
    print(f"Splitting '{input_path}' ({total} files from scan)...")

    photos_dir = OUTPUT_DIR / "photos" / folder_name
    youtube_dir = OUTPUT_DIR / "youtube" / folder_name
    unknown_dir = OUTPUT_DIR / "unknown" / folder_name
    for d in (photos_dir, youtube_dir, unknown_dir):
        d.mkdir(parents=True, exist_ok=True)

    counts = {"photo": 0, "video": 0, "unknown": 0}
    errors = []

    for i, entry in enumerate(files, 1):
        rel = entry["path"]          # e.g. "subdir/IMG_001.heic"
        kind = entry["type"]         # "photo" | "video" | "unknown"
        expected_size = entry["size"]

        src = input_path / rel
        if not src.exists():
            errors.append(f"  MISSING  {rel}")
            print(f"  [{i}/{total}] MISSING  {rel}")
            continue

        actual_size = src.stat().st_size
        if actual_size != expected_size:
            errors.append(f"  SIZE_MISMATCH  {rel}  (expected {expected_size}, got {actual_size})")
            print(f"  [{i}/{total}] SIZE_MISMATCH  {rel}")
            continue

        if kind == "photo":
            dst = photos_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
        elif kind == "video":
            # flat structure: join all path parts with "_" to avoid conflicts
            # e.g. "a/b/c/video.mp4" → "a_b_c_video.mp4"
            rel_path = Path(rel)
            new_name = "_".join(rel_path.parts)
            dst = youtube_dir / new_name
        else:
            dst = unknown_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(src, dst)

        copied_size = dst.stat().st_size
        if copied_size != expected_size:
            errors.append(f"  COPY_SIZE_MISMATCH  {rel}  (expected {expected_size}, got {copied_size})")
            print(f"  [{i}/{total}] COPY_SIZE_MISMATCH  {rel}")
            continue

        counts[kind] = counts.get(kind, 0) + 1
        index_by_path[rel].setdefault("lifecycle", []).append({"stage": "split", "at": _now()})
        print(f"  [{i}/{total}] {kind.upper():<7}  {rel}")

    copied_total = sum(counts.values())
    print(
        f"\nDone. {copied_total} files copied: "
        f"{counts['photo']} photos, {counts['video']} videos, {counts['unknown']} unknown"
    )

    # Post-copy file count check
    actual_photos = sum(1 for _ in photos_dir.rglob("*") if _.is_file())
    actual_videos = sum(1 for _ in youtube_dir.rglob("*") if _.is_file())
    actual_unknown = sum(1 for _ in unknown_dir.rglob("*") if _.is_file())

    count_ok = True
    for label, expected, actual in [
        ("photos", counts["photo"], actual_photos),
        ("videos", counts["video"], actual_videos),
        ("unknown", counts["unknown"], actual_unknown),
    ]:
        if expected != actual:
            print(f"  COUNT_MISMATCH {label}: expected {expected}, found {actual} on disk")
            count_ok = False

    with open(scan_json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    if errors:
        print(f"\n{len(errors)} error(s):")
        for e in errors:
            print(e)
    elif count_ok:
        print("All files verified OK.")
