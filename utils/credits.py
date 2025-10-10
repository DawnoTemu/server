from typing import Dict
import math


def get_credit_config() -> Dict[str, int | str]:
    """Return public credit configuration (label and unit size).

    This is a lightweight helper for routes/UI to avoid importing
    heavy modules when only the display config is required.
    """
    from config import Config

    raw_size = getattr(Config, "CREDITS_UNIT_SIZE", 1000)
    try:
        size = int(raw_size)
    except Exception:
        size = 1000
    if size <= 0:
        size = 1000
    return {
        "unit_label": getattr(Config, "CREDITS_UNIT_LABEL", "Story Points (Punkty Magii)"),
        "unit_size": size,
    }


def get_credit_sources_priority() -> list[str]:
    """Return normalized credit source priority order.

    - Strips whitespace and lowercases items
    - Deduplicates while preserving order
    - Accepts list/tuple or comma-separated string
    """
    from config import Config

    raw = getattr(
        Config,
        "CREDIT_SOURCES_PRIORITY",
        ["event", "monthly", "referral", "add_on", "free"],
    )

    if isinstance(raw, (list, tuple)):
        items = [str(x).strip().lower() for x in raw if str(x).strip()]
    else:
        items = [s.strip().lower() for s in str(raw).split(",") if s.strip()]

    seen = set()
    normalized: list[str] = []
    for s in items:
        if s not in seen:
            seen.add(s)
            normalized.append(s)
    return normalized


def calculate_required_credits(text: str | None, unit_size: int | None = None) -> int:
    """Calculate required Story Points for the given text length.

    - Uses ceil(len(text) / unit_size)
    - Minimum of 1 credit for any request (including empty text)
    - If `unit_size` is None or invalid (<=0), falls back to Config.CREDITS_UNIT_SIZE or 1000
    """
    if unit_size is None or not isinstance(unit_size, int) or unit_size <= 0:
        try:
            from config import Config
            cfg_val = int(getattr(Config, "CREDITS_UNIT_SIZE", 1000))
            unit_size = cfg_val if cfg_val > 0 else 1000
        except Exception:
            unit_size = 1000

    length = len(text) if text else 0
    credits = math.ceil(length / unit_size) if unit_size > 0 else 1
    return max(1, credits)
