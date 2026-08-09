import uuid


def new_id() -> str:
    """32-char hex id, matching neomodel's UniqueIdProperty (uuid4().hex).

    A plain CharField rather than UUIDField deliberately: UUIDField raises
    ValidationError on a malformed lookup value (e.g. a garbage URL path
    param), which turns an intended 404 into an unhandled 500. neomodel's
    UniqueIdProperty was a bare string with no such format validation, and
    every "get_or_none" lookup in the app relies on a non-matching id simply
    returning nothing — this preserves that.
    """
    return uuid.uuid4().hex
