"""ARVEN GUI — PySide6 desktop interface for the ARVEN backend.

This package is a pure interface layer. It imports only from ``gui`` plus the
existing ARVEN core (via ArvenBridge); nothing here is required by the core, the
terminal CLI or the voice modes. Deleting this directory removes the GUI and
leaves the rest of ARVEN fully functional.
"""

__version__ = "1.0.0"
__all__ = ["__version__"]