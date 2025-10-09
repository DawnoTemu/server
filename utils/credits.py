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
    """Return the configured credit sources consumption priority order."""
    from config import Config

    priority = getattr(Config, "CREDIT_SOURCES_PRIORITY", [
        "event",
        "monthly",
        "referral",
        "add_on",
        "free",
    ])
    # Ensure it's a list even if configured as a tuple
    return list(priority)

