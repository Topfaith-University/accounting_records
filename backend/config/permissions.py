from rest_framework.permissions import BasePermission


def require_roles(*roles):
    """Factory returning a permission class that allows only the specified Django Groups."""
    class RolePermission(BasePermission):
        def has_permission(self, request, view):
            if not request.user or not request.user.is_authenticated:
                return False
            return request.user.groups.filter(name__in=roles).exists()
    RolePermission.__name__ = f'Requires({",".join(roles)})'
    return RolePermission
