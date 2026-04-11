"""Workflow 3 — upload

Usage:
    python main.py upload <youtube_folder> [--title <playlist_title>]

For each video in output/youtube/<folder_name>/:
  1. Upload to YouTube (unlisted, not made for kids)
  2. Wait until YouTube finishes processing
  3. Add to playlist
  4. Verify: unlisted + file size + duration match
  5. Update index/<folder_name>.json with upload result

At the end, cross-checks the playlist against the log.
If all videos are verified, deletes output/youtube/<folder_name>/.

Skips already-verified videos on re-runs (idempotent).
State is stored in index/<folder_name>.json alongside the scan data.
"""

import json
import pickle
import shutil
import subprocess
import time
from pathlib import Path

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from utils import _now

BASE_DIR = Path(__file__).parent
SCAN_DIR = BASE_DIR / "index"
SECRETS_DIR = BASE_DIR / "secrets"
SCOPES = ["https://www.googleapis.com/auth/youtube"]
TOKEN_FILE = SECRETS_DIR / "token.pickle"
PROCESS_POLL_INTERVAL = 15   # seconds between processing status checks
PROCESS_TIMEOUT = 600        # max seconds to wait for YouTube processing
DURATION_POLL_INTERVAL = 5   # seconds between fileDetails polling
DURATION_TIMEOUT = 120       # max seconds to wait for durationMs


def _get_client_secret() -> Path:
    candidates = list(SECRETS_DIR.glob("client_secret*.json"))
    if not candidates:
        raise SystemExit("Error: no client_secret*.json found in secrets/")
    return candidates[0]


def _authenticate():
    creds = None
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                TOKEN_FILE.unlink(missing_ok=True)
                creds = None
        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(_get_client_secret()), SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return build("youtube", "v3", credentials=creds)


def _find_or_create_playlist(youtube, title: str) -> str:
    request = youtube.playlists().list(part="snippet", mine=True, maxResults=50)
    while request:
        response = request.execute()
        for item in response.get("items", []):
            if item["snippet"]["title"] == title:
                playlist_id = item["id"]
                print(f"Reusing existing playlist: '{title}' ({playlist_id})")
                return playlist_id
        request = youtube.playlists().list_next(request, response)

    response = youtube.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {"title": title},
            "status": {"privacyStatus": "unlisted"},
        },
    ).execute()
    playlist_id = response["id"]
    print(f"Created playlist: '{title}' ({playlist_id})")
    return playlist_id


def _upload_video(youtube, video_path: Path) -> str | None:
    body = {
        "snippet": {
            "title": video_path.stem,
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": "unlisted",
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(video_path), resumable=True)
    try:
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                print(f"    uploading {pct}%", end="\r", flush=True)
        video_id = response["id"]
        print(f"    uploaded  → https://youtu.be/{video_id}")
        return video_id
    except HttpError as e:
        if e.status_code == 403 and "quotaExceeded" in str(e):
            raise
        print(f"    ERROR uploading: {e}")
        return None


def _wait_until_processed(youtube, video_id: str) -> bool:
    """Poll until YouTube finishes processing. Returns True if processed."""
    start = time.time()
    while time.time() - start < PROCESS_TIMEOUT:
        response = youtube.videos().list(part="status", id=video_id).execute()
        items = response.get("items", [])
        if not items:
            # Video may not be indexed yet right after upload — keep polling
            elapsed = int(time.time() - start)
            print(f"    waiting for video to appear... ({elapsed}s)", end="\r", flush=True)
            time.sleep(PROCESS_POLL_INTERVAL)
            continue
        upload_status = items[0]["status"]["uploadStatus"]
        if upload_status == "processed":
            print("    processing done")
            return True
        if upload_status in ("failed", "rejected", "deleted"):
            print(f"    ERROR: processing ended with status '{upload_status}'")
            return False
        elapsed = int(time.time() - start)
        print(f"    processing... ({elapsed}s)", end="\r", flush=True)
        time.sleep(PROCESS_POLL_INTERVAL)
    print(f"    ERROR: timed out waiting for processing ({PROCESS_TIMEOUT}s)")
    return False


def _add_to_playlist(youtube, playlist_id: str, video_id: str) -> None:
    youtube.playlistItems().insert(
        part="snippet",
        body={
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {"kind": "youtube#video", "videoId": video_id},
            }
        },
    ).execute()


def _get_local_duration_ms(path: Path) -> int | None:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(float(result.stdout.strip()) * 1000)
    except Exception:
        pass
    return None


def _verify(youtube, video_id: str, local_size: int, video_path: Path) -> tuple[bool, list[str]]:
    """Verify video is unlisted, file size and duration match.
    Returns (verified, warnings) where warnings are non-fatal issues to log."""
    warnings: list[str] = []

    response = youtube.videos().list(
        part="status,fileDetails", id=video_id
    ).execute()
    items = response.get("items", [])
    if not items:
        print("    VERIFY FAILED: video not found on YouTube")
        return False, warnings

    item = items[0]
    privacy = item["status"]["privacyStatus"]
    if privacy != "unlisted":
        print(f"    VERIFY FAILED: expected unlisted, got '{privacy}'")
        return False, warnings

    file_details = item.get("fileDetails", {})

    yt_size = file_details.get("fileSize")
    if yt_size is not None and int(yt_size) != local_size:
        print(f"    VERIFY FAILED: size mismatch (local={local_size:,}, youtube={int(yt_size):,})")
        return False, warnings

    # Poll until durationMs is available
    local_ms = _get_local_duration_ms(video_path)
    yt_ms = file_details.get("durationMs")
    if local_ms is not None and yt_ms is None:
        start = time.time()
        while time.time() - start < DURATION_TIMEOUT:
            resp = youtube.videos().list(part="fileDetails", id=video_id).execute()
            yt_ms = resp.get("items", [{}])[0].get("fileDetails", {}).get("durationMs")
            if yt_ms is not None:
                break
            elapsed = int(time.time() - start)
            print(f"    waiting for durationMs... ({elapsed}s)", end="\r", flush=True)
            time.sleep(DURATION_POLL_INTERVAL)
        else:
            msg = f"durationMs not available after {DURATION_TIMEOUT}s"
            print(f"    WARNING: {msg}, skipping duration check")
            warnings.append(msg)

    if local_ms is not None and yt_ms is not None:
        if abs(int(yt_ms) - local_ms) > 1000:
            print(f"    VERIFY FAILED: duration mismatch (local={local_ms}ms, youtube={int(yt_ms)}ms)")
            return False, warnings
        duration_note = f", duration={local_ms:,}ms ✓"
    else:
        duration_note = ""

    size_note = f"size={local_size:,}" if yt_size is None else f"size={local_size:,} ✓"
    print(f"    verified ✓  (unlisted, {size_note}{duration_note})")
    return True, warnings


def _fetch_playlist_video_ids(youtube, playlist_id: str) -> set[str]:
    """Return the set of all video IDs currently in the playlist."""
    video_ids = set()
    request = youtube.playlistItems().list(
        part="snippet", playlistId=playlist_id, maxResults=50
    )
    while request:
        response = request.execute()
        for item in response.get("items", []):
            video_ids.add(item["snippet"]["resourceId"]["videoId"])
        request = youtube.playlistItems().list_next(request, response)
    return video_ids


def _load_index(scan_file: Path) -> dict:
    with open(scan_file, encoding="utf-8") as f:
        return json.load(f)


def _save_index(scan_file: Path, index: dict) -> None:
    with open(scan_file, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def upload(folder_name: str, playlist_title: str | None = None) -> None:
    index_file = SCAN_DIR / f"{folder_name}.json"
    if not index_file.exists():
        raise SystemExit(
            f"Error: '{index_file}' not found. Run 'python main.py scan <input_folder>' first."
        )

    index = _load_index(index_file)

    youtube_dir = Path(index["output_dir"]) / "youtube" / folder_name
    if not youtube_dir.is_dir():
        raise SystemExit(
            f"Error: '{youtube_dir}' not found. Run 'python main.py split {folder_name}' first."
        )

    # Build a lookup: youtube_filename → file entry (videos only)
    # youtube_filename matches what split.py produces: "_".join(Path(rel).parts)
    video_entries = {
        "_".join(Path(e["path"]).parts): e
        for e in index["files"]
        if e["type"] == "video"
    }

    videos = sorted(
        f for f in youtube_dir.iterdir() if f.is_file() and not f.name.startswith(".")
    )
    if not videos:
        print(f"No video files found in '{youtube_dir}' — nothing to upload.")
        return

    title = playlist_title or folder_name
    pending = [v for v in videos if not video_entries.get(v.name, {}).get("verified")]

    def _needs_reverify(v: Path) -> bool:
        e = video_entries.get(v.name, {})
        return not e.get("verified") and bool(e.get("video_url"))

    already_done = len(videos) - len(pending)
    if not pending:
        print(f"All {len(videos)} video(s) already verified. Nothing to do.")
        return
    if already_done:
        print(f"Skipping {already_done} already-verified video(s).")

    print(f"Processing {len(pending)} video(s) → playlist '{title}'...")

    youtube = _authenticate()
    playlist_id = index.get("playlist_id") or _find_or_create_playlist(youtube, title)

    index.setdefault("playlist_title", title)
    index["playlist_id"] = playlist_id
    _save_index(index_file, index)

    success = 0
    for i, video_path in enumerate(pending, 1):
        local_size = video_path.stat().st_size
        print(f"\n  [{i}/{len(pending)}] {video_path.name} ({local_size:,} bytes)")

        entry = video_entries.get(video_path.name)
        if entry is None:
            print(f"    WARNING: no scan entry found for '{video_path.name}', skipping")
            continue

        if _needs_reverify(video_path):
            # Already uploaded — just re-verify and re-add to playlist if needed
            video_id = entry["video_url"].split("/")[-1]
            print(f"    re-verifying previously uploaded video ({entry['video_url']})")
            _add_to_playlist(youtube, playlist_id, video_id)
        else:
            video_id = _upload_video(youtube, video_path)
            if not video_id:
                continue

            if not _wait_until_processed(youtube, video_id):
                continue

            _add_to_playlist(youtube, playlist_id, video_id)
            entry["youtube_filename"] = video_path.name
            entry["video_url"] = f"https://youtu.be/{video_id}"

        verified, verify_warnings = _verify(youtube, video_id, local_size, video_path)

        entry["verified"] = verified
        if verify_warnings:
            entry.setdefault("verify_warnings", []).extend(verify_warnings)
        entry.setdefault("lifecycle", []).append({"stage": "uploaded", "at": _now()})
        if verified:
            entry["lifecycle"].append({"stage": "verified", "at": _now()})
        _save_index(index_file, index)

        if verified:
            success += 1
        else:
            print(f"    upload logged but verification failed — folder will not be deleted")

    print(f"\nDone. {success}/{len(pending)} videos uploaded and verified.")

    # Final check: all local files verified in index AND confirmed in playlist
    not_in_log = [
        f.name for f in videos
        if not video_entries.get(f.name, {}).get("verified")
    ]
    if not_in_log:
        print(f"\nFolder kept — {len(not_in_log)} file(s) not yet verified: {not_in_log}")
        return

    print(f"\nAll {len(videos)} file(s) verified in index. Cross-checking playlist...")
    verified_video_ids = {
        e["video_url"].split("/")[-1] for e in video_entries.values() if e.get("verified")
    }
    playlist_video_ids = _fetch_playlist_video_ids(youtube, playlist_id)
    missing_from_playlist = verified_video_ids - playlist_video_ids
    if missing_from_playlist:
        missing_names = [
            name for name, e in video_entries.items()
            if e.get("video_url", "").split("/")[-1] in missing_from_playlist
        ]
        print(f"Folder kept — {len(missing_names)} video(s) missing from playlist: {missing_names}")
        return

    shutil.rmtree(youtube_dir)
    print(f"Playlist confirmed ({len(verified_video_ids)} video(s) present) — deleted folder '{youtube_dir}'.")
