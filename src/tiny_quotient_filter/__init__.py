"""Public API for tiny_quotient_filter.

Exports:
    QuotientFilter: A fixed-capacity quotient filter.
    FullError: Raised when inserting into a full filter.
"""

from .core import QuotientFilter, FullError

__all__ = ["QuotientFilter", "FullError"]
