In this folder you will find the files listed below. Complete the work described next.

`pager.py` `paginate(total, page, per_page)` : rend un dict {"page", "pages", "offset", "limit", "has_prev",
"has_next"}. pages = max(1, ceil(total / per_page)). `page` hors bornes est ramene dans [1, pages] (jamais d erreur).
offset = (page-1)*per_page ; limit = nombre reel d elements de cette page (la derniere peut etre plus courte ; 0 si
total == 0). per_page < 1 ou total < 0 : ValueError.
