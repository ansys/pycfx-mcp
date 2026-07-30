# Copyright (C) 2026 Synopsys, Inc. and ANSYS, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""In-memory conversation/clarification store with TTL.

Used to track multi-turn `codegen` <-> `clarify` interactions so the LLM
caller can be stateless (it only needs to keep `session_id` and
`clarification_id`).

Extensible: swap `_now()` and the dict for a Redis-backed implementation
later without touching the rest of the codebase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import threading
import time
from typing import Any, Optional
import uuid


@dataclass
class ConversationEntry:
    """Conversation state tracked for a code generation session."""

    session_id: str
    created_at: float
    updated_at: float
    history: list[dict[str, Any]] = field(default_factory=list)
    pending_clarification: Optional[dict[str, Any]] = None
    extra: dict[str, Any] = field(default_factory=dict)


class ConversationStore:
    """Thread-safe TTL-bounded conversation store."""

    def __init__(self, *, ttl_seconds: float = 60 * 60, max_entries: int = 256) -> None:
        """Initialize this object with the dependencies required for later operations.

        Parameters
        ----------
        ttl_seconds : float, optional
            Number of seconds a conversation can remain idle before eviction. Default is ``60 *
            60``.
        max_entries : int, optional
            Maximum number of conversations retained in the store. Default is ``256``.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """
        self._ttl = ttl_seconds
        self._max = max_entries
        self._lock = threading.RLock()
        self._entries: dict[str, ConversationEntry] = {}

    @staticmethod
    def _now() -> float:
        """Return the current timestamp used for conversation expiry checks.

        Returns
        -------
        float
            Floating-point score, timestamp, or metric for the requested operation.
        """
        return time.monotonic()

    # ---- lifecycle ---------------------------------------------------

    def create(self) -> ConversationEntry:
        """Create and store a new code-generation conversation entry.

        Returns
        -------
        ConversationEntry
            Value computed by the helper for the requested CFX workflow.
        """
        with self._lock:
            self._evict_locked()
            sid = uuid.uuid4().hex
            entry = ConversationEntry(
                session_id=sid, created_at=self._now(), updated_at=self._now()
            )
            self._entries[sid] = entry
            return entry

    def get(self, session_id: str) -> Optional[ConversationEntry]:
        """Return an existing conversation entry by session identifier.

        Parameters
        ----------
        session_id : str
            Conversation identifier used to retrieve or continue context.

        Returns
        -------
        Optional[ConversationEntry]
            Value computed by the helper for the requested CFX workflow.
        """
        with self._lock:
            entry = self._entries.get(session_id)
            if entry is None:
                return None
            if self._now() - entry.updated_at > self._ttl:
                self._entries.pop(session_id, None)
                return None
            return entry

    def get_or_create(self, session_id: Optional[str]) -> ConversationEntry:
        """Return an existing conversation entry or create a new one.

        Parameters
        ----------
        session_id : Optional[str]
            Conversation identifier used to retrieve or continue context.

        Returns
        -------
        ConversationEntry
            Requested CFX data or metadata for the active session.
        """
        if session_id:
            entry = self.get(session_id)
            if entry is not None:
                return entry
        return self.create()

    def touch(self, session_id: str) -> None:
        """Refresh the last-used time for a conversation entry.

        Parameters
        ----------
        session_id : str
            Conversation identifier used to retrieve or continue context.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """
        with self._lock:
            entry = self._entries.get(session_id)
            if entry is not None:
                entry.updated_at = self._now()

    def append_history(self, session_id: str, role: str, content: Any) -> None:
        """Append one message to a conversation history.

        Parameters
        ----------
        session_id : str
            Conversation identifier used to retrieve or continue context.
        role : str
            Conversation message role, such as user or assistant.
        content : Any
            Conversation message content to store.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """
        with self._lock:
            entry = self._entries.get(session_id)
            if entry is None:
                return
            entry.history.append({"role": role, "content": content, "ts": self._now()})
            entry.updated_at = self._now()

    def set_pending_clarification(
        self, session_id: str, clarification: dict[str, Any] | None
    ) -> None:
        """Record the clarification currently awaiting a user answer.

        Parameters
        ----------
        session_id : str
            Conversation identifier used to retrieve or continue context.
        clarification : dict[str, Any] | None
            Clarification payload currently waiting for a user answer.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """
        with self._lock:
            entry = self._entries.get(session_id)
            if entry is not None:
                entry.pending_clarification = clarification
                entry.updated_at = self._now()

    def has_pending_clarification_id(self, session_id: str, clarification_id: str) -> bool:
        """Return whether a conversation is waiting for a specific clarification.

        Parameters
        ----------
        session_id : str
            Conversation identifier used to retrieve or continue context.
        clarification_id : str
            Identifier of the clarification being answered or checked.

        Returns
        -------
        bool
            Boolean answer for the requested condition.
        """
        with self._lock:
            entry = self._entries.get(session_id)
            if entry is None or entry.pending_clarification is None:
                return False
            return entry.pending_clarification.get("id") == clarification_id

    def clarification_was_just_asked(self, session_id: str, question_text: str) -> bool:
        """Return whether a clarification was asked very recently.

        Parameters
        ----------
        session_id : str
            Conversation identifier used to retrieve or continue context.
        question_text : str
            Clarification question text shown to the user.

        Returns
        -------
        bool
            Boolean answer for the requested condition.
        """
        with self._lock:
            entry = self._entries.get(session_id)
            if entry is None or entry.pending_clarification is None:
                return False
            existing = (entry.pending_clarification.get("question") or "").strip().lower()
            return bool(existing) and existing == (question_text or "").strip().lower()

    # ---- maintenance -------------------------------------------------

    def _evict_locked(self) -> None:
        """Evict expired or excess conversation entries while holding the store lock.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """
        if len(self._entries) < self._max:
            # Always opportunistically drop expired entries.
            cutoff = self._now() - self._ttl
            stale = [sid for sid, e in self._entries.items() if e.updated_at < cutoff]
            for sid in stale:
                self._entries.pop(sid, None)
            return
        # Capacity hit: drop oldest first.
        ordered = sorted(self._entries.items(), key=lambda kv: kv[1].updated_at)
        for sid, _ in ordered[: max(1, len(self._entries) - self._max + 1)]:
            self._entries.pop(sid, None)
