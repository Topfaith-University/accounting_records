"""Shared server-side pagination helpers for neomodel-backed ViewSets.

Every hand-written `ViewSet.list()` in this codebase fetches its full NodeSet
and returns a bare array — DRF's pagination_class machinery never runs since
none of these are GenericAPIView-based. These helpers give call sites an
explicit, opt-in way to paginate a NodeSet at the Cypher level (SKIP/LIMIT +
a real count query) instead of materializing everything into Python.
"""

import math

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


def parse_pagination_params(request, default_page_size=DEFAULT_PAGE_SIZE, max_page_size=MAX_PAGE_SIZE):
    try:
        page = int(request.query_params.get('page', 1))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(request.query_params.get('page_size', default_page_size))
    except (TypeError, ValueError):
        page_size = default_page_size

    page = max(1, page)
    page_size = min(max(1, page_size), max_page_size)
    return page, page_size


def paginate_nodeset(qs, page, page_size):
    """Slice a neomodel NodeSet server-side. `len(qs)` and `qs[skip:skip+size]`
    each issue their own Cypher query (COUNT and ORDER BY...SKIP...LIMIT
    respectively) rather than materializing the full result set.
    """
    total = len(qs)
    skip = (page - 1) * page_size
    items = list(qs[skip:skip + page_size])
    return total, items


def paginated_response(total, page, page_size, serialized_results):
    return {
        'count': total,
        'page': page,
        'page_size': page_size,
        'total_pages': max(1, math.ceil(total / page_size)),
        'results': serialized_results,
    }
