"""Holds the current request's resolved Business in a contextvar, set by
BusinessMiddleware after tenant resolution — never guess it elsewhere.
Not populated outside a request (management commands, shell): code running
there should query Business explicitly and use raw_objects."""
from contextvars import ContextVar

_current_business_id = ContextVar("current_business_id", default=None)


def set_current_business(business):
    _current_business_id.set(business.pk if business else None)


def get_current_business_id():
    return _current_business_id.get()
