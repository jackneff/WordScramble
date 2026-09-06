"""HTTP layer: page routes and the JSON API."""
from routes.api import bp as api_bp
from routes.lists import bp as lists_bp
from routes.pages import bp as pages_bp
from routes.players import bp as players_bp

__all__ = ["api_bp", "lists_bp", "pages_bp", "players_bp"]
