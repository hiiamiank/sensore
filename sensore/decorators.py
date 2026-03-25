"""
decorators.py — Sensore Application

Custom access-control decorators used by views.py.
"""

from functools import wraps
from django.shortcuts import redirect
from django.http import HttpResponseForbidden
from django.contrib import messages


def role_required(*roles):
    """
    Restricts a view to users whose role is in the given list.

    Usage:
        @role_required('admin')
        @role_required('clinician', 'admin')

    - Unauthenticated users → redirected to login.
    - Wrong role → 403 Forbidden.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if request.user.role not in roles:
                return HttpResponseForbidden(
                    f"Access denied. Required role(s): {', '.join(roles)}."
                )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator