import math


def paginate(total, page, per_page):
    if per_page < 1:
        raise ValueError("per_page must be >= 1")
    if total < 0:
        raise ValueError("total must be >= 0")

    pages = math.ceil(total / per_page)

    if page < 1 or page > pages:
        raise ValueError("page out of bounds")

    offset = (page - 1) * per_page
    limit = per_page

    has_prev = page > 1
    has_next = page < pages

    return {
        "page": page,
        "pages": pages,
        "offset": offset,
        "limit": limit,
        "has_prev": has_prev,
        "has_next": has_next,
    }

