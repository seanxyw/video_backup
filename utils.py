from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
