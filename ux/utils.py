from django.core.paginator import EmptyPage, Paginator
from django.http import QueryDict
from django.utils.http import url_has_allowed_host_and_scheme


def paginate(request, items, per_page=20):
    paginator = Paginator(items, per_page)
    try:
        page = paginator.page(request.GET.get('page') or 1)
    except (EmptyPage, ValueError):
        page = paginator.page(paginator.num_pages or 1)
    params = request.GET.copy()
    params.pop('page', None)
    return page, params.urlencode()


def safe_next(request, default):
    """POST/GET dagi `next` faqat shu saytga ishora qilsa qabul qilinadi."""
    nxt = request.POST.get('next') or request.GET.get('next') or ''
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return nxt
    return default
