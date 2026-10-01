"""Tests sloppy.cli._already_ingested_handles - the helper backing `slop ingest
seed-channels`'s skip-if-already-ingested behavior. Added after the user asked whether
re-running seed-channels.csv after adding new rows would re-scrape already-done channels
(it did, with no skip logic at all) - this closes that gap. Follows the project's
"keep CLI commands thin, test the real logic directly" convention: there is no CliRunner
invocation here, just a direct test of the extracted helper against real Postgres.
"""

from datetime import UTC, datetime

from sloppy.cli import _already_ingested_handles
from sloppy.db.models import Channel
from sloppy.db.session import session_scope

DONE_ID = "UC_test_seed_channels_done"
PENDING_ID = "UC_test_seed_channels_pending"
NO_HANDLE_ID = "UC_test_seed_channels_no_handle"


def _cleanup() -> None:
    with session_scope() as session:
        session.query(Channel).filter(Channel.id.in_([DONE_ID, PENDING_ID, NO_HANDLE_ID])).delete(
            synchronize_session=False
        )


def test_already_ingested_handles_only_includes_channels_with_last_ingested_at_set():
    _cleanup()
    try:
        with session_scope() as session:
            session.add(
                Channel(
                    id=DONE_ID,
                    handle="@DoneChannel",
                    title="Done Channel",
                    uploads_playlist_id="UU_done",
                    last_ingested_at=datetime.now(UTC),
                )
            )
            session.add(
                Channel(
                    id=PENDING_ID,
                    handle="@PendingChannel",
                    title="Pending Channel",
                    uploads_playlist_id="UU_pending",
                    last_ingested_at=None,
                )
            )
            # A channel with no handle at all must not blow up the lowercasing - excluded.
            session.add(
                Channel(
                    id=NO_HANDLE_ID,
                    handle=None,
                    title="No Handle Channel",
                    uploads_playlist_id="UU_no_handle",
                    last_ingested_at=datetime.now(UTC),
                )
            )

        with session_scope() as session:
            done_handles = _already_ingested_handles(session)

        # This runs against the real dev DB, which already holds real previously-ingested
        # seed channels - so assert on the fixtures' presence/absence, not the total count.
        # Lowercased, matching how YouTube's customUrl is always stored - a CSV entry
        # spelled with different casing (e.g. "@donechannel") must still be recognized.
        assert "@donechannel" in done_handles
        assert "@pendingchannel" not in done_handles
        assert "@no_handle" not in done_handles
    finally:
        _cleanup()
