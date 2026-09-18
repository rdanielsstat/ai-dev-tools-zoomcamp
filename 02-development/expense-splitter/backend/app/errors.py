"""Domain errors raised by the store layer. Translated to HTTP responses by
the exception handlers registered in main.py, so the store stays free of any
HTTP-specific concerns (useful once it's swapped for a real DB layer)."""


class NotFoundError(Exception):
    """Also raised when the group/expense exists but the caller isn't a
    member — membership is never revealed to non-members."""


class ForbiddenError(Exception):
    """Authenticated, but not allowed to perform this action (e.g. non-admin
    deleting a group)."""


class ConflictError(Exception):
    """E.g. signing up with an email that's already registered."""


class BadRequestError(Exception):
    """E.g. a split that doesn't reconcile to the expense total."""


class UnauthorizedError(Exception):
    """Missing or invalid credentials / bearer token."""
