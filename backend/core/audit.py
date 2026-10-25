import json
import logging

from .models import AuditLog

logger = logging.getLogger(__name__)


def log_action(request, action, target=None, details=None, actor=None):
    """Record who did what. A problem here must never break the action itself."""
    try:
        user = actor or getattr(request, "user", None)
        if user is not None and not getattr(user, "is_authenticated", False):
            user = None
        ip = request.META.get("REMOTE_ADDR") if request is not None else None
        return AuditLog.objects.create(
            actor=user,
            action=action,
            target_type=type(target).__name__ if target is not None else "",
            target_id=str(target.pk) if target is not None else "",
            target_repr=str(target)[:200] if target is not None else "",
            details=json.loads(json.dumps(details or {}, default=str)),
            ip_address=ip or None,
        )
    except Exception:
        logger.exception("Could not write audit log entry %s", action)
        return None
