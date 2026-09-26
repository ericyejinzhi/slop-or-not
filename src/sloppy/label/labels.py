"""Recording labeling judgments.

record_label is a plain INSERT, not an upsert - no ON CONFLICT semantics apply here.
Relabeling the same video deliberately adds a new row rather than overwriting the old one
(see db.models.Label).
"""

from sqlalchemy.orm import Session

from sloppy.db.models import Label


def record_label(
    session: Session, *, video_id: str, labeler: str, label: str, notes: str | None = None
) -> None:
    session.add(Label(video_id=video_id, labeler=labeler, label=label, notes=notes))
