"""Time utilities.

Python 3.12+ deprecates ``datetime.utcnow()`` and ``datetime.utcfromtimestamp()``
in favor of timezone-aware alternatives (``datetime.now(UTC)``,
``datetime.fromtimestamp(ts, tz=UTC)``). However, the SQLAlchemy ``DateTime``
columns used throughout this project are declared without ``timezone=True``,
which means they store and return *naive* datetimes. Comparing a naive
datetime to a timezone-aware datetime raises ``TypeError``.

Rather than migrate every column to ``DateTime(timezone=True)`` (risky,
requires a careful Alembic migration that interprets existing naive rows as
UTC), we provide helper functions that return naive UTC datetimes. These are
drop-in replacements for the deprecated calls and preserve the existing
semantics exactly.

If the DB schema is ever migrated to timezone-aware columns, simply change
these helpers to return timezone-aware datetimes — every caller updates at
once.
"""

from datetime import datetime, timezone


def utc_now():
    """Return the current UTC time as a naive ``datetime``.

    Drop-in replacement for ``datetime.utcnow()``. Matches its semantics
    exactly (naive datetime representing UTC) but avoids the Python 3.12+
    deprecation warning.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_from_timestamp(ts):
    """Return a naive UTC ``datetime`` from a POSIX timestamp.

    Drop-in replacement for ``datetime.utcfromtimestamp(ts)``. Matches its
    semantics exactly (naive UTC datetime) but avoids the Python 3.12+
    deprecation warning.
    """
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
