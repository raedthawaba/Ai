"""Workers package — sections 6.2-6.8.

Import the celery app only when needed to avoid import chain issues.
"""
__all__ = ["app"]


def __getattr__(name: str):
    if name == "app":
        from .celery_app import app
        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
