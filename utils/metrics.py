import logging


def emit_metric(name: str, value: float = 1.0, **tags):
    """Lightweight metrics hook; replace with real client (StatsD, Prometheus) in prod."""
    logging.getLogger("metrics").info("metric", extra={"metric": name, "value": value, **tags})

