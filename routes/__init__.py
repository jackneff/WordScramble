"""HTTP layer: page routes and the JSON API."""
from routes.api import bp as api_bp
from routes.pages import bp as pages_bp

__all__ = ["api_bp", "pages_bp"]
