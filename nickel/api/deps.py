"""FastAPI dependencies."""

from api.auth import audit_action, check_permission, get_current_user, require_admin

__all__ = [
    "get_current_user",
    "check_permission",
    "audit_action",
    "require_admin",
    "assert_fact_access",
    "apply_search_acl",
]
