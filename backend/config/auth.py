"""Shared helpers for reading the active company/role off a request's validated JWT.

Every company-scoped view (ViewSet or function-based) should use these instead of
`request.user.groups` for authorization, and instead of a bare `Model.nodes.all()`
for data access — role and data visibility are both scoped to the *active company*
carried in the token, not globally per-user.
"""


def get_active_company_id(request):
    """Returns the active company_id claim from the validated JWT, or None for a
    pre-company token (user has 0 or >1 memberships and hasn't called
    /api/auth/switch-company/ yet)."""
    auth = getattr(request, 'auth', None)
    if auth is None:
        return None
    return auth.get('company_id')


def get_active_role(request):
    auth = getattr(request, 'auth', None)
    if auth is None:
        return None
    return auth.get('role')


def is_admin(request):
    return get_active_role(request) == 'Admin'
