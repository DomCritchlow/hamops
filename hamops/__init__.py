"""Hamops package exports."""

# Re-export application factory for convenience
from .main import create_app

__all__ = ["create_app"]
