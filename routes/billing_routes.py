from flask import jsonify, request

from routes import billing_bp
from utils.auth_middleware import token_required
from utils.rate_limiter import limiter
from utils.credits import get_credit_config, calculate_required_credits
from models.credit_model import get_user_credit_summary, get_user_transactions
from models.story_model import StoryModel


def _parse_transaction_types(arg_value: str | None):
    if not arg_value:
        return None
    parts = [segment.strip() for segment in arg_value.split(",")]
    return [part for part in parts if part]


@billing_bp.route('/me/credits', methods=['GET'])
@token_required
@limiter.limit("30 per minute")
def get_my_credits(current_user):
    cfg = get_credit_config()

    history_limit = request.args.get('history_limit', type=int)
    if history_limit is None:
        history_limit = 20
    history_limit = max(1, min(history_limit, 100))

    history_offset = max(request.args.get('history_offset', type=int) or 0, 0)
    types_param = request.args.get('type') or request.args.get('types')
    history_types = _parse_transaction_types(types_param)

    summary = get_user_credit_summary(
        current_user.id,
        history_limit=history_limit,
        history_offset=history_offset,
        history_types=history_types,
    )
    summary['unit_label'] = cfg['unit_label']
    summary['unit_size'] = cfg['unit_size']
    # Surface cached vs computed for reconciliation visibility
    summary['balance_source'] = 'computed'

    return jsonify(summary), 200


@billing_bp.route('/me/credits/history', methods=['GET'])
@token_required
@limiter.limit("30 per minute")
def get_my_credit_history(current_user):
    limit = request.args.get('limit', type=int)
    if limit is None:
        limit = 20
    limit = max(1, min(limit, 100))

    offset = max(request.args.get('offset', type=int) or 0, 0)
    types_param = request.args.get('type') or request.args.get('types')
    tx_types = _parse_transaction_types(types_param)

    history = get_user_transactions(
        current_user.id,
        limit=limit,
        offset=offset,
        tx_types=tx_types,
    )
    return jsonify(history), 200


@billing_bp.route('/stories/<int:story_id>/credits', methods=['GET'])
def get_story_credits(story_id):
    story = StoryModel.get_story_by_id(story_id)
    if not story:
        return jsonify({'error': 'Story not found'}), 404
    text = story.get('content') or ''
    required = calculate_required_credits(text)
    return jsonify({'required_credits': required}), 200
