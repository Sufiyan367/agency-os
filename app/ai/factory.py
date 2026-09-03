import os
from typing import Optional
from app.ai.base import BaseAIProvider
from app.ai.mock import MockAIProvider
from app.ai.gemini import GeminiProvider

_active_provider: Optional[BaseAIProvider] = None

def get_ai_provider(provider_type: Optional[str] = None) -> BaseAIProvider:
    """
    Factory resolving the active BaseAIProvider implementation.
    Defaults to 'mock' if not configured or if in local development mode.
    """
    global _active_provider
    selected = provider_type or os.getenv("AI_PROVIDER", "mock").lower()

    if selected == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            return GeminiProvider(api_key=api_key)
        # Safe fallback
        return MockAIProvider()
    
    return MockAIProvider()

def reset_ai_provider():
    global _active_provider
    _active_provider = None
