"""WSGI entrypoint for the controlled LexiBridge pilot server."""

from app import app as application


__all__ = ["application"]
