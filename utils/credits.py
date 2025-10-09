from typing import Dict


def get_credit_config() -> Dict[str, int | str]:
    """Return public credit configuration (label and unit size).

    This is a lightweight helper for routes/UI to avoid importing
    heavy modules when only the display config is required.
    """
    from config import Config

    return {
        "unit_label": getattr(Config, "CREDITS_UNIT_LABEL", "Story Points (Punkty Magii)"),
        "unit_size": int(getattr(Config, "CREDITS_UNIT_SIZE", 1000)),
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
