"""Postgres-backed LangGraph checkpoint setup for interview sessions."""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg.rows import dict_row

from app.core.config import get_settings


_CHECKPOINT_SCHEMA = "agentic_grc_private"


def _connection_string() -> str:
    return get_settings().sqlalchemy_url.set(drivername="postgresql").render_as_string(
        hide_password=False
    )


@contextmanager
def open_interview_checkpointer() -> Iterator[PostgresSaver]:
    """Open a checkpointer connection scoped to the private checkpoint schema.

    Graph state should remain JSON-compatible. The empty MsgPack allowlist blocks
    arbitrary Python object deserialization from checkpoint data.
    """
    with psycopg.connect(
        _connection_string(), autocommit=True, row_factory=dict_row
    ) as connection:
        connection.execute(f"SET search_path TO {_CHECKPOINT_SCHEMA}")
        yield PostgresSaver(
            connection,
            serde=JsonPlusSerializer(allowed_msgpack_modules=()),
        )


def initialize_interview_checkpointer() -> None:
    """Create or upgrade the LangGraph-owned checkpoint tables in Postgres."""
    with open_interview_checkpointer() as checkpointer:
        checkpointer.setup()


def interview_thread_config(session_id: UUID) -> dict[str, dict[str, str]]:
    """Use the persisted assessment session as the stable, tenant-scoped thread id."""
    return {"configurable": {"thread_id": str(session_id)}}
