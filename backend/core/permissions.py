from rest_framework.permissions import BasePermission


def crud_permissions(app, model):
    """Permission map for a staff ViewSet. DELETE needs only 'change' because it deactivates."""
    view, change = f"{app}.view_{model}", f"{app}.change_{model}"
    return {
        "list": view,
        "retrieve": view,
        "create": f"{app}.add_{model}",
        "update": change,
        "partial_update": change,
        "destroy": change,
    }


class StaffPermission(BasePermission):
    """Staff only, and only for the actions listed in the view's permission_map."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_active and user.is_staff):
            return False
        key = getattr(view, "action", None) or request.method.lower()
        required = getattr(view, "permission_map", {}).get(key)
        if required is None:
            return False  # anything not listed is refused
        if isinstance(required, str):
            required = [required]
        return user.has_perms(required)
