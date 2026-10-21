"""Predict-specific failures. Deliberately NOT ValueError subclasses: the app maps every
ValueError to 404 (see api/errors.py), and these need their own status codes."""


class InvalidVideoLink(Exception):
    """The pasted text names no single YouTube video."""


class VideoNotFound(Exception):
    """YouTube has no public video with that id (deleted, private, or mistyped)."""


class PredictionUnavailable(Exception):
    """The server cannot make predictions right now: no model configured, a model that
    needs channel history, or YouTube unreachable / out of quota."""
