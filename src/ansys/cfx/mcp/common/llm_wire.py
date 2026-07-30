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

"""Wire helpers for LiteLLM/OpenAI-compatible chat endpoints."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import time
from typing import Any, Sequence

DEFAULT_MODEL = "gpt-4o-mini"
logger = logging.getLogger(__name__)
_TLS_INSECURE_WARNED = False


@dataclass(frozen=True)
class ModelConfig:
    """Resolved chat endpoint configuration."""

    endpoint: str | None
    api_key: str | None
    model: str
    auth_style: str = "bearer"


class LLMTransportError(RuntimeError):
    """Raised when an LLM transport call fails."""


PROVIDER_OPENAI = "openai"
PROVIDER_AZURE = "azure"
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_GEMINI = "gemini"
PROVIDER_COMPAT = "compat"

TRANSPORT_LITELLM = "litellm"
TRANSPORT_COMPAT = "openai_compat"

_KNOWN_PROVIDERS = frozenset(
    {PROVIDER_OPENAI, PROVIDER_AZURE, PROVIDER_ANTHROPIC, PROVIDER_GEMINI, PROVIDER_COMPAT}
)
_PROVIDER_KEY_ENVS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "AZURE_API_KEY",
    "LLM_API_KEY",
)


@dataclass(frozen=True)
class RetrySpec:
    """Retry/backoff policy for LLM transport calls."""

    max_attempts: int = 3
    backoff_base: float = 0.5
    timeout_s: float = 60.0


@dataclass(frozen=True)
class LLMProfile:
    """Resolved provider and transport settings for an LLM call."""

    provider: str
    model: str
    route: str
    endpoint: str | None
    transport: str
    retry: RetrySpec
    auth_style: str = "bearer"


def env_flag(name: str, *, default: bool, env=os.environ) -> bool:
    """Read a boolean environment flag using common truthy and falsy strings.

    Parameters
    ----------
    name : str
        Name of the object, resource, or field to process.
    default : bool
        Fallback value used when no explicit setting is present.
    env : Any, optional
        Environment mapping used to resolve LLM configuration. Default is ``os.environ``.

    Returns
    -------
    bool
        Boolean answer for the requested condition.
    """
    raw = env.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def resolve_tls_verify(env=os.environ) -> bool | str:
    """Resolve TLS verification settings for outbound LLM HTTP requests.

    Parameters
    ----------
    env : Any, optional
        Environment mapping used to resolve LLM configuration. Default is ``os.environ``.

    Returns
    -------
    bool | str
        Value computed by the helper for the requested CFX workflow.
    """
    global _TLS_INSECURE_WARNED
    if env_flag("LLM_TLS_INSECURE", default=False, env=env):
        if not _TLS_INSECURE_WARNED:
            logger.warning(
                "LLM_TLS_INSECURE is set: TLS certificate verification is disabled "
                "for outbound LLM calls. Prefer LLM_CA_BUNDLE instead."
            )
            _TLS_INSECURE_WARNED = True
        return False
    for var in ("LLM_CA_BUNDLE", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        path = (env.get(var) or "").strip()
        if path:
            return path
    return True


def first_model_token(raw: str | None) -> str | None:
    """Return the first model identifier from a comma-separated model list.

    Parameters
    ----------
    raw : str | None
        Raw payload returned by PyCFX or a provider API.

    Returns
    -------
    str | None
        Value computed by the helper for the requested CFX workflow.
    """
    if not raw or not raw.strip():
        return None
    return raw.split()[0]


def normalize_endpoint(url: str) -> str:
    """Normalize an LLM endpoint URL by removing trailing slashes.

    Parameters
    ----------
    url : str
        Endpoint URL to normalize or inspect.

    Returns
    -------
    str
        String value produced for the requested CFX or provider operation.
    """
    cleaned = url.rstrip("/")
    if cleaned.endswith("/chat/completions"):
        return cleaned
    return f"{cleaned}/chat/completions"


def resolve_model_config(
    *,
    endpoint: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    auth_style: str | None = None,
    env=os.environ,
) -> ModelConfig:
    """Resolve provider, transport, endpoint, and model settings from the environment.

    Parameters
    ----------
    endpoint : str | None, optional
        Provider endpoint used for the LLM request. Default is ``None``.
    api_key : str | None, optional
        API key used to authenticate the provider request. Default is ``None``.
    model : str | None, optional
        Model identifier selected for the request. Default is ``None``.
    auth_style : str | None, optional
        Authorization-header style required by the provider. Default is ``None``.
    env : Any, optional
        Environment mapping used to resolve LLM configuration. Default is ``os.environ``.

    Returns
    -------
    ModelConfig
        Value computed by the helper for the requested CFX workflow.
    """
    raw_endpoint = endpoint or env.get("LLM_ENDPOINT") or None
    return ModelConfig(
        endpoint=normalize_endpoint(raw_endpoint) if raw_endpoint else None,
        api_key=api_key or env.get("LLM_API_KEY") or None,
        model=model or first_model_token(env.get("LLM_MODEL")) or DEFAULT_MODEL,
        auth_style=(auth_style or env.get("LLM_AUTH_STYLE") or "bearer").lower(),
    )


def detect_provider(model: str | None, endpoint: str | None, *, env=os.environ) -> str:
    """Infer the LLM provider from an explicit provider, model name, or endpoint URL.

    Parameters
    ----------
    model : str | None
        Model identifier selected for the request.
    endpoint : str | None
        Provider endpoint used for the LLM request.
    env : Any, optional
        Environment mapping used to resolve LLM configuration. Default is ``os.environ``.

    Returns
    -------
    str
        String value produced for the requested CFX or provider operation.
    """
    explicit = (env.get("LLM_PROVIDER") or "").strip().lower()
    if explicit in _KNOWN_PROVIDERS:
        return explicit

    name = (model or "").strip().lower()
    if "/" in name:
        prefix = name.split("/", 1)[0]
        if prefix in _KNOWN_PROVIDERS:
            return prefix
        if prefix in {"vertex_ai", "google"}:
            return PROVIDER_GEMINI

    if endpoint:
        from urllib.parse import urlparse

        host = (urlparse(endpoint).hostname or "").lower()
        if "azure" in host:
            return PROVIDER_AZURE
        if "anthropic" in host:
            return PROVIDER_ANTHROPIC
        if "googleapis" in host or "gemini" in host:
            return PROVIDER_GEMINI
        if "openai.com" in host:
            return PROVIDER_OPENAI
        if host:
            return PROVIDER_COMPAT

    if name.startswith("claude"):
        return PROVIDER_ANTHROPIC
    if name.startswith("gemini"):
        return PROVIDER_GEMINI
    return PROVIDER_OPENAI


def resolve_litellm_route(provider: str, model: str) -> str:
    """Resolve the LiteLLM model route and API key for the selected provider.

    Parameters
    ----------
    provider : str
        LLM provider name selected for the request.
    model : str
        Model identifier selected for the request.

    Returns
    -------
    str
        String value produced for the requested CFX or provider operation.
    """
    name = (model or "").strip()
    if "/" in name:
        return name
    if provider == PROVIDER_AZURE:
        return f"azure/{name}"
    if provider == PROVIDER_ANTHROPIC:
        return f"anthropic/{name}"
    if provider == PROVIDER_GEMINI:
        return f"gemini/{name}"
    if provider == PROVIDER_OPENAI:
        return f"openai/{name}"
    return name


def native_provider_configured(model: str | None, *, env=os.environ) -> bool:
    """Return whether a native provider has enough configuration to run.

    Parameters
    ----------
    model : str | None
        Model identifier selected for the request.
    env : Any, optional
        Environment mapping used to resolve LLM configuration. Default is ``os.environ``.

    Returns
    -------
    bool
        Boolean answer for the requested condition.
    """
    if (env.get("LLM_PROVIDER") or "").strip():
        return True
    name = (model or "").strip().lower()
    if "/" in name or name.startswith("claude") or name.startswith("gemini"):
        return True
    return any((env.get(key) or "").strip() for key in _PROVIDER_KEY_ENVS)


def resolve_profile(
    *,
    model: str | None = None,
    endpoint: str | None = None,
    auth_style: str | None = None,
    env=os.environ,
) -> LLMProfile:
    """Resolve the full LLM wire profile used for model calls.

    Parameters
    ----------
    model : str | None, optional
        Model identifier selected for the request. Default is ``None``.
    endpoint : str | None, optional
        Provider endpoint used for the LLM request. Default is ``None``.
    auth_style : str | None, optional
        Authorization-header style required by the provider. Default is ``None``.
    env : Any, optional
        Environment mapping used to resolve LLM configuration. Default is ``os.environ``.

    Returns
    -------
    LLMProfile
        Value computed by the helper for the requested CFX workflow.
    """
    cfg = resolve_model_config(endpoint=endpoint, model=model, auth_style=auth_style, env=env)
    provider = detect_provider(cfg.model, cfg.endpoint, env=env)
    transport = (env.get("LLM_TRANSPORT") or "auto").strip().lower()
    if transport not in (TRANSPORT_LITELLM, TRANSPORT_COMPAT, "auto"):
        transport = "auto"
    if transport == "auto":
        if cfg.endpoint:
            transport = TRANSPORT_COMPAT
        elif native_provider_configured(cfg.model, env=env):
            transport = TRANSPORT_LITELLM
        else:
            transport = TRANSPORT_COMPAT

    try:
        max_attempts = int(env.get("LLM_MAX_RETRIES") or 3)
    except (TypeError, ValueError):
        max_attempts = 3
    try:
        timeout_s = float(env.get("LLM_TIMEOUT_SECONDS") or 60.0)
    except (TypeError, ValueError):
        timeout_s = 60.0

    return LLMProfile(
        provider=provider,
        model=cfg.model,
        route=resolve_litellm_route(provider, cfg.model),
        endpoint=cfg.endpoint,
        transport=transport,
        retry=RetrySpec(max_attempts=max(1, max_attempts), timeout_s=timeout_s),
        auth_style=cfg.auth_style,
    )


_MODEL_QUIRKS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("gpt-5", {"max_tokens_param": "max_completion_tokens", "send_temperature": False}),
    ("o1", {"max_tokens_param": "max_completion_tokens", "send_temperature": False}),
    ("o3", {"max_tokens_param": "max_completion_tokens", "send_temperature": False}),
    ("o4", {"max_tokens_param": "max_completion_tokens", "send_temperature": False}),
)


def resolve_model_quirks(model: str) -> dict[str, Any]:
    """Resolve request-format quirks required by the selected model.

    Parameters
    ----------
    model : str
        Model identifier selected for the request.

    Returns
    -------
    dict[str, Any]
        Structured response payload for the requested operation.
    """
    name = (model or "").lower()
    for prefix, quirks in _MODEL_QUIRKS:
        if name.startswith(prefix):
            return dict(quirks)
    return {}


def max_tokens_param_for(model: str) -> str:
    """Return the max-token request parameter name for a provider and model.

    Parameters
    ----------
    model : str
        Model identifier selected for the request.

    Returns
    -------
    str
        String value produced for the requested CFX or provider operation.
    """
    return os.environ.get("LLM_MAX_TOKENS_PARAM") or resolve_model_quirks(model).get(
        "max_tokens_param", "max_tokens"
    )


def send_temperature_for(model: str) -> bool:
    """Return whether temperature should be sent for a provider and model.

    Parameters
    ----------
    model : str
        Model identifier selected for the request.

    Returns
    -------
    bool
        Boolean answer for the requested condition.
    """
    return env_flag(
        "LLM_SEND_TEMPERATURE",
        default=resolve_model_quirks(model).get("send_temperature", True),
    )


def build_chat_body(
    *,
    model: str,
    messages: Sequence[dict[str, Any]],
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> dict[str, Any]:
    """Build an OpenAI-compatible chat-completions request body.

    Parameters
    ----------
    model : str
        Model identifier selected for the request.
    messages : Sequence[dict[str, Any]]
        Chat messages to send to the model.
    max_tokens : int | None, optional
        Maximum number of tokens requested from the model. Default is ``None``.
    temperature : float | None, optional
        Sampling temperature for providers that support it. Default is ``None``.

    Returns
    -------
    dict[str, Any]
        Structured response payload for the requested operation.
    """
    body: dict[str, Any] = {"model": model, "messages": list(messages)}
    if max_tokens is not None:
        body[max_tokens_param_for(model)] = max_tokens
    if temperature is not None and send_temperature_for(model):
        body["temperature"] = temperature
    return body


def build_litellm_kwargs(
    profile: LLMProfile,
    messages: Sequence[dict[str, Any]],
    *,
    max_tokens: int | None = None,
    temperature: float | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    api_version: str | None = None,
) -> dict[str, Any]:
    """Build keyword arguments for a LiteLLM completion call.

    Parameters
    ----------
    profile : LLMProfile
        Resolved LLM provider profile used to build requests.
    messages : Sequence[dict[str, Any]]
        Chat messages to send to the model.
    max_tokens : int | None, optional
        Maximum number of tokens requested from the model. Default is ``None``.
    temperature : float | None, optional
        Sampling temperature for providers that support it. Default is ``None``.
    api_key : str | None, optional
        API key used to authenticate the provider request. Default is ``None``.
    api_base : str | None, optional
        Provider API base URL override. Default is ``None``.
    api_version : str | None, optional
        Provider API version override, when required. Default is ``None``.

    Returns
    -------
    dict[str, Any]
        Structured response payload for the requested operation.
    """
    kwargs: dict[str, Any] = {
        "model": profile.route,
        "messages": list(messages),
        "num_retries": 0,
        "drop_params": True,
    }
    if max_tokens is not None:
        kwargs[max_tokens_param_for(profile.model)] = max_tokens
    if temperature is not None and send_temperature_for(profile.model):
        kwargs["temperature"] = temperature
    if api_key:
        kwargs["api_key"] = api_key
    if api_base:
        kwargs["api_base"] = api_base
    if api_version:
        kwargs["api_version"] = api_version
    return kwargs


def auth_headers(
    api_key: str | None,
    *,
    auth_style: str = "bearer",
    base: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build HTTP authorization headers for an LLM provider profile.

    Parameters
    ----------
    api_key : str | None
        API key used to authenticate the provider request.
    auth_style : str, optional
        Authorization-header style required by the provider. Default is ``'bearer'``.
    base : dict[str, str] | None, optional
        Existing headers to extend. Default is ``None``.

    Returns
    -------
    dict[str, str]
        Value computed by the helper for the requested CFX workflow.
    """
    headers = dict(base) if base else {"Content-Type": "application/json"}
    if api_key:
        if (auth_style or "bearer").lower() == "azure-api-key":
            headers["api-key"] = api_key
        else:
            headers["Authorization"] = f"Bearer {api_key}"
    return headers


def extract_chat_text(payload: dict[str, Any]) -> str:
    """Extract assistant text from a chat-completion provider response.

    Parameters
    ----------
    payload : dict[str, Any]
        Structured payload to process.

    Returns
    -------
    str
        String value produced for the requested CFX or provider operation.
    """
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        return content if isinstance(content, str) else ""
    text = first.get("text")
    return text if isinstance(text, str) else ""


def _import_litellm():
    """Import LiteLLM and raise a clear configuration error if it is unavailable.

    Returns
    -------
    Any
        Value computed by the helper for the requested CFX workflow.
    """
    try:
        import litellm  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise LLMTransportError(
            "litellm is required for native multi-provider transport; "
            "install with `pip install ansys-cfx-mcp[providers]`."
        ) from exc
    try:
        litellm.telemetry = False
    except Exception:
        logger.debug("Failed to disable LiteLLM telemetry", exc_info=True)
    return litellm


def _compat_call(
    profile: LLMProfile,
    messages: Sequence[dict[str, Any]],
    *,
    max_tokens: int | None,
    temperature: float | None,
    api_key: str | None,
) -> dict[str, Any]:
    """Call a synchronous function with only the keyword arguments it accepts.

    Parameters
    ----------
    profile : LLMProfile
        Resolved LLM provider profile used to build requests.
    messages : Sequence[dict[str, Any]]
        Chat messages to send to the model.
    max_tokens : int | None
        Maximum number of tokens requested from the model.
    temperature : float | None
        Sampling temperature for providers that support it.
    api_key : str | None
        API key used to authenticate the provider request.

    Returns
    -------
    dict[str, Any]
        Structured response payload for the requested operation.
    """
    if not profile.endpoint:
        raise LLMTransportError("LLM_ENDPOINT is required for openai_compat transport.")
    import requests

    body = build_chat_body(
        model=profile.model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    response = requests.post(
        profile.endpoint,
        json=body,
        headers=auth_headers(api_key, auth_style=profile.auth_style),
        timeout=profile.retry.timeout_s,
        verify=resolve_tls_verify(),
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise LLMTransportError("LLM endpoint returned a non-object response.")
    return payload


def call(
    profile: LLMProfile,
    messages: Sequence[dict[str, Any]],
    *,
    max_tokens: int | None = None,
    temperature: float | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    api_version: str | None = None,
) -> dict[str, Any]:
    """Send a synchronous chat-completion request through the configured LLM transport.

    Parameters
    ----------
    profile : LLMProfile
        Resolved LLM provider profile used to build requests.
    messages : Sequence[dict[str, Any]]
        Chat messages to send to the model.
    max_tokens : int | None, optional
        Maximum number of tokens requested from the model. Default is ``None``.
    temperature : float | None, optional
        Sampling temperature for providers that support it. Default is ``None``.
    api_key : str | None, optional
        API key used to authenticate the provider request. Default is ``None``.
    api_base : str | None, optional
        Provider API base URL override. Default is ``None``.
    api_version : str | None, optional
        Provider API version override, when required. Default is ``None``.

    Returns
    -------
    dict[str, Any]
        Structured response payload for the requested operation.
    """
    last_exc: Exception | None = None
    for attempt in range(profile.retry.max_attempts):
        try:
            if profile.transport == TRANSPORT_LITELLM:
                litellm = _import_litellm()
                kwargs = build_litellm_kwargs(
                    profile,
                    messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    api_key=api_key,
                    api_base=api_base,
                    api_version=api_version,
                )
                response = litellm.completion(timeout=profile.retry.timeout_s, **kwargs)
                return response.model_dump() if hasattr(response, "model_dump") else dict(response)
            return _compat_call(
                profile,
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
                api_key=api_key,
            )
        except LLMTransportError:
            raise
        except Exception as exc:
            last_exc = exc
            if attempt + 1 >= profile.retry.max_attempts:
                break
            time.sleep(profile.retry.backoff_base * (2**attempt))
    raise LLMTransportError(f"LLM call failed: {last_exc}") from last_exc


async def acall(
    profile: LLMProfile,
    messages: Sequence[dict[str, Any]],
    *,
    max_tokens: int | None = None,
    temperature: float | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    api_version: str | None = None,
) -> dict[str, Any]:
    """Send an asynchronous chat-completion request through the configured LLM transport.

    Parameters
    ----------
    profile : LLMProfile
        Resolved LLM provider profile used to build requests.
    messages : Sequence[dict[str, Any]]
        Chat messages to send to the model.
    max_tokens : int | None, optional
        Maximum number of tokens requested from the model. Default is ``None``.
    temperature : float | None, optional
        Sampling temperature for providers that support it. Default is ``None``.
    api_key : str | None, optional
        API key used to authenticate the provider request. Default is ``None``.
    api_base : str | None, optional
        Provider API base URL override. Default is ``None``.
    api_version : str | None, optional
        Provider API version override, when required. Default is ``None``.

    Returns
    -------
    dict[str, Any]
        Structured response payload for the requested operation.
    """
    import asyncio

    return await asyncio.to_thread(
        call,
        profile,
        messages,
        max_tokens=max_tokens,
        temperature=temperature,
        api_key=api_key,
        api_base=api_base,
        api_version=api_version,
    )


# ---------------------------------------------------------------------------
# AALI models.yaml fallback
#
# The shared agent engine forwards to these two names. Ported here so the CFX
# path can source the AALI model loader from ``ansys.cfx.mcp.common.llm_wire``
# without pulling another product package into the import path.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AaliChatModel:
    """A single resolved chat-model entry from the AALI models config."""

    endpoint: str
    api_key: str | None
    model: str
    model_type: str
    auth_style: str  # "bearer" or "azure-api-key"
    source: Path


_CONFIG_DIR = Path("Ansys") / "Aali" / "config"
# AALI has shipped both ``models.config`` and ``models.yaml`` over time;
# probe every known filename in priority order. ``models.yaml`` is the
# current AALI default; ``models.config`` is the legacy name (probed last).
_CONFIG_FILENAMES = ("models.yaml", "models.yml", "models.config")


def _aali_candidate_paths() -> list[Path]:
    """Ordered list of locations to probe for the AALI models file.

    Returns
    -------
    list[Path]
        Collection containing the operation results.
    """
    roots: list[Path] = []

    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        roots.append(Path(local_app))

    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        roots.append(Path(xdg))
    home = Path.home()
    roots.append(home / ".local" / "share")
    roots.append(home / "Library" / "Application Support")  # macOS

    paths: list[Path] = [root / _CONFIG_DIR / name for root in roots for name in _CONFIG_FILENAMES]

    override = os.environ.get("AALI_MODELS_CONFIG")
    if override:
        paths.insert(0, Path(override))

    return paths


def _looks_like_azure(url: str, model_type: str) -> bool:
    """Return whether the endpoint appears to be an Azure OpenAI endpoint.

    Parameters
    ----------
    url : str
        Endpoint URL used by the client or backend.
    model_type : str
        Model type supplied to the function.

    Returns
    -------
    bool
        Boolean result of the operation.
    """
    return "azure.com" in url.lower() or model_type.lower().startswith("azure")


def load_aali_chat_model() -> AaliChatModel | None:
    """Return the first usable chat model from the AALI config, or ``None``.

    Never raises: any I/O or parse error is logged and yields ``None`` so
    the caller can fall back to its own defaults.

    Returns
    -------
    AaliChatModel | None
        Result produced by the function.
    """
    try:
        import yaml  # PyYAML — optional dependency
    except ImportError:
        logger.debug("PyYAML not installed; skipping AALI models config lookup")
        return None

    for path in _aali_candidate_paths():
        try:
            if not path.is_file():
                continue
        except OSError:
            continue
        try:
            with path.open("r", encoding="utf-8") as fh:
                doc = yaml.safe_load(fh) or {}
        except (OSError, yaml.YAMLError) as exc:
            logger.warning("Could not read AALI models config at %s: %s", path, exc)
            continue

        chat_models = doc.get("CHAT_MODELS") if isinstance(doc, dict) else None
        if not isinstance(chat_models, list) or not chat_models:
            continue

        first = chat_models[0]
        if not isinstance(first, dict):
            continue

        url = str(first.get("URL", "")).strip()
        if not url:
            continue
        model = str(first.get("MODEL_NAME", "")).strip() or DEFAULT_MODEL
        model_type = str(first.get("MODEL_TYPE", "")).strip()
        api_key_raw = first.get("API_KEY")
        api_key = str(api_key_raw).strip() if api_key_raw else None
        if api_key and api_key.lower() in {"none", "null", ""}:
            api_key = None

        endpoint = normalize_endpoint(url)
        auth_style = "azure-api-key" if _looks_like_azure(url, model_type) else "bearer"

        logger.info(
            "Loaded LLM defaults from AALI models config (%s): model=%s endpoint=%s",
            path,
            model,
            endpoint,
        )
        return AaliChatModel(
            endpoint=endpoint,
            api_key=api_key,
            model=model,
            model_type=model_type or "openai",
            auth_style=auth_style,
            source=path,
        )

    return None
