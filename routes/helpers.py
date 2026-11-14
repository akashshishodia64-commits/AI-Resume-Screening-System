"""Shared route helpers."""
from functools import wraps
from urllib.parse import urlparse

from flask import abort, flash, g, redirect, request, url_for


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            flash("Please sign in to continue.", "info")
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)
    return wrapped


def safe_next(target, fallback="dashboard.index"):
    """Only allow same-site relative redirects (prevents open redirects)."""
    if target:
        parsed = urlparse(target)
        if not parsed.scheme and not parsed.netloc and target.startswith("/") and not target.startswith("//"):
            return target
    return url_for(fallback)


def owned_or_404(row):
    if row is None:
        abort(404)
    return row
