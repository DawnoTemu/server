import logging

from tasks import celery_app
from utils.metrics import emit_metric
from models.user_model import UserModel


logger = logging.getLogger("account_tasks")


@celery_app.task(
    name="account.delete_user_account",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def delete_user_account(user_id: int):
    """Async account deletion task to avoid long HTTP waits."""
    success, details = UserModel.delete_user(user_id)
    if not success:
        logger.error(
            "Account deletion failed",
            extra={"user_id": user_id, "error": str(details)},
        )
        raise Exception(details)
    logger.info(
        "Account deletion completed",
        extra={"user_id": user_id, "warnings": details.get("warnings", []) if isinstance(details, dict) else []},
    )
    emit_metric("account.deletion.complete")
    return {"warnings": details.get("warnings", []) if isinstance(details, dict) else []}
