"""Tests the two centralized exception handlers directly. Both are largely defense in
depth given the current API surface: GET /videos/{id}'s 404 uses an explicit
session.get(...) check (see test_api_videos.py), not the ValueError handler (no endpoint
today raises a ValueError synchronously - ingest_video's ValueError only happens inside a
BackgroundTask, invisible to the HTTP response by design), and POST /labels' 422 for an
invalid label value comes from Pydantic's Literal validation before the DB is ever
touched (see test_api_labels.py), making the label CHECK-constraint IntegrityError path
unreachable through the API as designed. So the handlers themselves are tested directly
here, and their registration on the real app is confirmed separately.
"""

import asyncio
import json

from sqlalchemy.exc import IntegrityError

from sloppy.api.app import app
from sloppy.api.errors import integrity_error_handler, value_error_handler


def test_value_error_handler_returns_404_with_message():
    response = asyncio.run(value_error_handler(None, ValueError("No YouTube video found for 'x'")))
    assert response.status_code == 404
    assert json.loads(response.body) == {"detail": "No YouTube video found for 'x'"}


def test_integrity_error_handler_returns_409():
    exc = IntegrityError("INSERT INTO labels ...", {}, Exception("duplicate key value"))
    response = asyncio.run(integrity_error_handler(None, exc))
    assert response.status_code == 409
    body = json.loads(response.body)
    assert body["detail"] == "Conflicting or invalid data"
    assert "duplicate key value" in body["error"]


def test_handlers_are_registered_on_the_app():
    assert app.exception_handlers[ValueError] is value_error_handler
    assert app.exception_handlers[IntegrityError] is integrity_error_handler
