"""Adapter registry.

Adding an aggregator means writing one module and adding one line here.
"""
from ..constants import AggregatorType
from .base import (
    AdapterError, AuthError, BaseAdapter, NotSupported, SignatureError, UpstreamError,
)
from .gofood import GoFoodAdapter
from .grabfood import GrabFoodAdapter
from .shopeefood import ShopeeFoodAdapter

_ADAPTERS = {
    AggregatorType.GOFOOD: GoFoodAdapter,
    AggregatorType.GRABFOOD: GrabFoodAdapter,
    AggregatorType.SHOPEEFOOD: ShopeeFoodAdapter,
}


def get_adapter_class(aggregator: str):
    try:
        return _ADAPTERS[aggregator]
    except KeyError as exc:
        raise NotSupported(f'Aggregator tidak dikenal: {aggregator}') from exc


def get_adapter(credential) -> BaseAdapter:
    """Build the adapter for a stored credential."""
    return get_adapter_class(credential.aggregator)(credential)


__all__ = [
    'AdapterError', 'AuthError', 'BaseAdapter', 'NotSupported', 'SignatureError',
    'UpstreamError', 'GoFoodAdapter', 'GrabFoodAdapter', 'ShopeeFoodAdapter',
    'get_adapter', 'get_adapter_class',
]
