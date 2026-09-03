import os
from typing import Optional
from app.providers.base import BaseMessageProvider
from app.providers.mock import MockMessageProvider

_singleton_provider: Optional[BaseMessageProvider] = None

def get_message_provider(provider_type: Optional[str] = None) -> BaseMessageProvider:
    global _singleton_provider
    if _singleton_provider is None:
        _singleton_provider = MockMessageProvider()
    return _singleton_provider

def reset_message_provider():
    global _singleton_provider
    _singleton_provider = None
