from flask import jsonify
from datetime import datetime

from routes import billing_bp
from utils.auth_middleware import token_required
from utils.credits import get_credit_config, calculate_required_credits
from models.credit_model import CreditLot, CreditTransaction
from models.story_model import StoryModel


@billing_bp.route('/me/credits', methods=['GET'])
@token_required
def get_my_credits(current_user):
    cfg = get_credit_config()
    now = datetime.utcnow()

    # Active lots (non-expired, positive remaining)
    lots_q = (
        CreditLot.query
        .filter(
            CreditLot.user_id == current_user.id,
            CreditLot.amount_remaining > 0,
            (CreditLot.expires_at.is_(None) | (CreditLot.expires_at > now)),
        )
        .order_by(CreditLot.expires_at.asc(), CreditLot.created_at)
    )
    lots = [
        {
            'source': l.source,
            'amount_remaining': int(l.amount_remaining or 0),
            'expires_at': l.expires_at.isoformat() if l.expires_at else None,
        }
        for l in lots_q.all()
    ]

    # Recent transactions (last 20)
    tx_q = (
        CreditTransaction.query
        .filter(CreditTransaction.user_id == current_user.id)
        .order_by(CreditTransaction.created_at.desc())
        .limit(20)
    )
    transactions = [
        {
            'type': t.type,
            'amount': int(t.amount),
            'status': t.status,
            'reason': t.reason,
            'audio_story_id': t.audio_story_id,
            'story_id': t.story_id,
            'created_at': t.created_at.isoformat() if t.created_at else None,
        }
        for t in tx_q.all()
    ]

    return jsonify({
        'balance': int(current_user.credits_balance or 0),
        'unit_label': cfg['unit_label'],
        'unit_size': cfg['unit_size'],
        'lots': lots,
        'recent_transactions': transactions,
    }), 200


@billing_bp.route('/stories/<int:story_id>/credits', methods=['GET'])
def get_story_credits(story_id):
    story = StoryModel.get_story_by_id(story_id)
    if not story:
        return jsonify({'error': 'Story not found'}), 404
    text = story.get('content') or ''
    required = calculate_required_credits(text)
    return jsonify({'required_credits': required}), 200
