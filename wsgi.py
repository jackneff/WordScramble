"""WSGI entry point for production servers.

    gunicorn --bind 127.0.0.1:8000 wsgi:app
"""
from app import create_app

app = create_app()
