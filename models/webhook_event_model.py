from datetime import datetime

from database import db
from utils.time_utils import utc_now


class WebhookEvent(db.Model):
    """Tracks processed webhook event IDs for idempotent handling.

    RevenueCat may deliver the same event more than once.  Before processing,
    check whether the event_id already exists in this table.
    """

    __tablename__ = 'webhook_events'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
    event_type = db.Column(db.String(50), nullable=False)
    processed_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)
