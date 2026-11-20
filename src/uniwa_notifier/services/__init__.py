"""Πύλη Φοιτητολογίου (services.uniwa.gr) μέσω του κεντρικού SSO του ΠΑΔΑ."""
from .client import Services, ServicesError

__all__ = ["Services", "ServicesError"]
