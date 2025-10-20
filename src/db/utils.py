from datetime import datetime, timezone

def utcnow() -> datetime:
    """UTC now - shared across models and processing."""
    return datetime.now(timezone.utc)
