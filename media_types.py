PHOTO_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif",
    ".dng", ".raf", ".cr2", ".cr3", ".gpr",
    ".insp", ".tiff", ".tif",
}

VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".mts", ".m2ts", ".insv",
    ".avi", ".mkv",
}

EXCLUDED_EXTENSIONS = {".lrv", ".thm", ".ds_store"}

EXCLUDED_FILENAMES = {".ds_store", ".gitkeep"}


def classify(path: str) -> str:
    """Return 'photo', 'video', 'unknown', or 'excluded'."""
    filename = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
    if filename in EXCLUDED_FILENAMES:
        return "excluded"
    ext = f".{filename.rsplit('.', 1)[-1]}" if "." in filename else ""
    if ext in EXCLUDED_EXTENSIONS:
        return "excluded"
    if ext in PHOTO_EXTENSIONS:
        return "photo"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    return "unknown"
