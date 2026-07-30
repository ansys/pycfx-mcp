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

"""Extensible code-generation pipeline.

In Phase 1, the pipeline forwards `(prompt, session_id)` to the backend
`codegen` method, which usually calls the existing Fluids One
`/api/chat/propose_code` endpoint.

In Phase 3, the LLM orchestration loop moves into this module so the MCP
server itself drives the generation by calling backend tools directly for
named objects, state, and allowed values. Until then, this file gives every
leaf a single, consistent place to evolve the pipeline.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ansys.cfx.mcp.common.backend import Backend
from ansys.cfx.mcp.common.conversation import ConversationStore
from ansys.cfx.mcp.common.errors import BackendUnavailable, InvalidArguments, NotConnected
from ansys.cfx.mcp.common.llm_wire import (
    LLMTransportError,
    acall,
    extract_chat_text,
    native_provider_configured,
    resolve_model_config,
    resolve_profile,
)
from ansys.cfx.mcp.common.models import CodegenResult

logger = logging.getLogger("ansys.cfx.mcp.codegen")

_CFX_CODEGEN_SYSTEM_PROMPT = (
    "Generate concise Python snippets for Ansys CFX workflows using PyCFX. "
    "Return only Python code unless a short code comment is required.\n"
    "Emit the MINIMAL code that satisfies the request. Do not invent or assign "
    "extra settings, locations, boundary conditions, or numeric values that the "
    "user did not ask for. When the user only asks to create an object, create "
    "just that object with its type; leave optional values unset."
)


class CodegenPipeline:
    """Default pipeline: delegate to the backend.

    Subclass and override `generate` / `clarify` to add LLM orchestration,
    retrieval, validation passes, etc.
    """

    def __init__(self, *, store: ConversationStore) -> None:
        """Initialize this object with the dependencies required for later operations.

        Parameters
        ----------
        store : ConversationStore
            Conversation store used to track code-generation context.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """
        self.store = store

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    async def generate(
        self,
        *,
        backend: Backend,
        prompt: str,
        session_id: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> CodegenResult:
        """Generate CFX Python code or a clarification response from a user prompt.

        Parameters
        ----------
        backend : Backend
            Backend that provides CFX state, validation, and execution services.
        prompt : str
            Natural-language user request to process.
        session_id : Optional[str], optional
            Conversation identifier used to retrieve or continue context. Default is ``None``.
        context : Optional[dict[str, Any]], optional
            Additional context supplied by the caller. Default is ``None``.

        Returns
        -------
        CodegenResult
            Generated-code response or clarification request.
        """
        if not prompt or not prompt.strip():
            raise InvalidArguments("prompt must be a non-empty string")
        supports_disconnected_codegen = bool(
            getattr(backend, "supports_disconnected_codegen", False)
        )
        if not backend.is_connected() and not supports_disconnected_codegen:
            raise NotConnected("Call `connect` before `codegen`.")

        entry = self.store.get_or_create(session_id)
        self.store.append_history(entry.session_id, "user", prompt)

        try:
            result = await backend.codegen(
                prompt=prompt,
                session_id=entry.session_id,
                context=context,
            )
        except BackendUnavailable:
            result = await self._generate_with_llm(prompt=prompt)

        # Carry our internal session id through so multi-turn clarify works.
        if result.session_id is None:
            result.session_id = entry.session_id

        self._record_result(entry.session_id, result)
        return result

    async def clarify(
        self, *, backend: Backend, session_id: str, clarification_id: str, answer: str
    ) -> CodegenResult:
        """Continue code generation after a clarification answer.

        Parameters
        ----------
        backend : Backend
            Backend that provides CFX state, validation, and execution services.
        session_id : str
            Conversation identifier used to retrieve or continue context.
        clarification_id : str
            Identifier of the clarification being answered or checked.
        answer : str
            User answer to the clarification prompt.

        Returns
        -------
        CodegenResult
            Generated-code response or clarification request.
        """
        if not session_id:
            raise InvalidArguments("session_id is required")
        if not clarification_id:
            raise InvalidArguments("clarification_id is required")

        entry = self.store.get(session_id)
        if entry is None:
            raise InvalidArguments(f"Unknown or expired session_id: {session_id}")
        if not backend.is_connected():
            raise NotConnected("Call `connect` before `clarify`.")

        self.store.append_history(
            session_id,
            "user",
            {"clarification_id": clarification_id, "answer": answer},
        )

        result = await backend.clarify(
            session_id=session_id,
            clarification_id=clarification_id,
            answer=answer,
        )
        if result.session_id is None:
            result.session_id = session_id

        self._record_result(session_id, result)
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _generate_with_llm(self, *, prompt: str) -> CodegenResult:
        """Generate CFX Python code with the configured language-model fallback.

        Parameters
        ----------
        prompt : str
            Natural-language user request to process.

        Returns
        -------
        CodegenResult
            Generated-code response or clarification request.
        """
        config = resolve_model_config()
        if not config.endpoint and not native_provider_configured(config.model):
            return CodegenResult(
                status="error",
                error_code="llm_not_configured",
                message=(
                    "Optional LLM fallback is not configured. Set LLM_ENDPOINT for an "
                    "OpenAI-compatible endpoint, or configure a native provider key and install "
                    "ansys-cfx-mcp[providers]."
                ),
            )

        profile = resolve_profile(
            model=config.model, endpoint=config.endpoint, auth_style=config.auth_style
        )
        system_prompt = self._compose_system_prompt(prompt)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        try:
            payload = await acall(
                profile,
                messages,
                max_tokens=700,
                temperature=0,
                api_key=config.api_key,
                api_base=config.endpoint if profile.transport == "litellm" else None,
            )
        except LLMTransportError as exc:
            return CodegenResult(status="error", error_code="llm_call_failed", message=str(exc))

        code = extract_chat_text(payload).strip()
        if not code:
            return CodegenResult(
                status="error",
                error_code="llm_empty_response",
                message="The optional LLM fallback returned no code.",
            )
        code = self._ground_code(code)
        return CodegenResult(status="ok", code=code)

    @staticmethod
    def _compose_system_prompt(prompt: str) -> str:
        """Compose the system prompt used for CFX code generation.

        Parameters
        ----------
        prompt : str
            Natural-language user request to process.

        Returns
        -------
        str
            String value produced for the requested CFX or provider operation.
        """
        try:
            from ansys.cfx.mcp.cfx.recipes import match_recipes, recipes_prompt_block

            block = recipes_prompt_block(match_recipes(prompt))
            if block:
                return _CFX_CODEGEN_SYSTEM_PROMPT + "\n\n" + block
        except Exception:  # pragma: no cover - defensive, never block codegen
            logger.debug("CFX recipe grounding skipped due to error", exc_info=True)
        return _CFX_CODEGEN_SYSTEM_PROMPT

    @staticmethod
    def _ground_code(code: str) -> str:
        """Apply schema grounding to generated CFX Python code.

        Parameters
        ----------
        code : str
            Python source code submitted for validation, grounding, or execution.

        Returns
        -------
        str
            String value produced for the requested CFX or provider operation.
        """
        try:
            from ansys.cfx.mcp.cfx.grounding import ground_code

            grounded, report = ground_code(code)
            if report.changed:
                logger.info(
                    "CFX schema grounding fixed %d attribute(s): %s",
                    len(report.replacements),
                    report.replacements,
                )
            return grounded
        except Exception:  # pragma: no cover - defensive, never block codegen
            logger.debug("CFX schema grounding skipped due to error", exc_info=True)
            return code

    def _record_result(self, session_id: str, result: CodegenResult) -> None:
        """Record a code-generation result in the conversation history.

        Parameters
        ----------
        session_id : str
            Conversation identifier used to retrieve or continue context.
        result : CodegenResult
            Run-code result passed to observers or recorded in history.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """
        self.store.append_history(session_id, "assistant", result.model_dump())
        if result.status == "needs_clarification" and result.clarifications:
            # Store the first pending clarification as the "current" one so
            # the LLM/UI can answer without re-sending the whole list.
            self.store.set_pending_clarification(session_id, result.clarifications[0].model_dump())
        else:
            self.store.set_pending_clarification(session_id, None)
