from django.shortcuts import render

from .base import ux_login


@ux_login()
def coming_soon(request, **kwargs):
    return render(request, 'new/coming_soon.html', {})
