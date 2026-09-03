"""Per-stage provider and model settings, and the provider status the admin
panel shows.

Resolution order for one model call, most specific first:

    settings["stages"][<stage key>]   → settings["default"]   → environment

Only `provider` and `model` are configurable: both enter the recording cache
key in `common/llm.py`, so a stage pointed at a different model honestly
misses every recording made under the old one — a replay run then fails
loudly rather than serving another model's output as this one's.

Stage keys are the workflow ids from `factory/layers.py`; the development
lane's three roles have their own keys so an independent reviewer can run on
a second model without touching the developer's (the REVIEW_LLM_* environment
variables remain the fallback for the reviewer key).
"""

from __future__ import annotations

import os
import shutil
from typing import Any

from s7_delivery.product import config

FILE = "llm_settings.json"

PROVIDERS = ("anthropic", "openai", "bedrock", "ollama", "custom", "claude_cli")
MODES = ("live", "record", "replay")

# (key, label, group). Keys match `layers.WORKFLOWS` ids, plus the lane roles.
STAGES: tuple[tuple[str, str, str], ...] = (
    ("requirement-extraction", "Requirement extraction", "intake"),
    ("requirement-routing", "Requirement routing", "intake"),
    ("intake-analysis", "Intake analysis", "intake"),
    ("clarification", "Clarification round", "intake"),
    ("new-application-setup", "New-application setup", "intake"),
    ("new-application-scaffold", "New-application scaffold", "intake"),
    ("epic-decomposition", "Epic decomposition", "planning"),
    ("architecture-refine", "Architecture refine", "build_review"),
    ("test-plan-refine", "Test-plan refine", "build_review"),
    ("development-lane.developer", "Developer (lane)", "build_review"),
    ("development-lane.tester", "Tester (lane)", "build_review"),
    ("development-lane.reviewer", "Independent reviewer (lane)", "build_review"),
    ("staged-pipeline", "Staged pipeline (assess / design / stories)", "legacy"),
    ("prompt-improve", "Prompt improvement (correction learning, admin only)", "admin"),
)
STAGE_KEYS = tuple(k for k, _, _ in STAGES)

_EMPTY: dict[str, Any] = {"default": {"provider": None, "model": None},
                          "stages": {}, "llm_mode": None}


def _clean_entry(entry: Any, where: str) -> dict[str, str | None]:
    if entry is None:
        return {"provider": None, "model": None}
    if not isinstance(entry, dict):
        raise config.ConfigError(f"{where}: expected an object with provider/model")
    provider = entry.get("provider") or None
    model = entry.get("model") or None
    if provider is not None:
        provider = str(provider).lower()
        if provider not in PROVIDERS:
            raise config.ConfigError(
                f"{where}: unknown provider {provider!r}; expected one of {', '.join(PROVIDERS)}"
            )
    if model is not None:
        model = str(model).strip() or None
    return {"provider": provider, "model": model}


def validate(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise config.ConfigError("llm settings must be an object")
    out: dict[str, Any] = {
        "default": _clean_entry(data.get("default"), "default"),
        "stages": {},
        "llm_mode": None,
    }
    stages = data.get("stages") or {}
    if not isinstance(stages, dict):
        raise config.ConfigError("stages must be an object keyed by stage")
    for key, entry in stages.items():
        if key not in STAGE_KEYS:
            raise config.ConfigError(
                f"unknown stage {key!r}; expected one of {', '.join(STAGE_KEYS)}"
            )
        cleaned = _clean_entry(entry, f"stages.{key}")
        if cleaned["provider"] or cleaned["model"]:
            out["stages"][key] = cleaned
    mode = data.get("llm_mode") or None
    if mode is not None:
        mode = str(mode).lower()
        if mode not in MODES:
            raise config.ConfigError(f"llm_mode must be one of {', '.join(MODES)}")
    out["llm_mode"] = mode
    return out


def load() -> dict[str, Any]:
    return validate(config.read_json(FILE, _EMPTY))


def save(data: Any, *, actor: str = "") -> dict[str, Any]:
    before = load()
    cleaned = validate(data)
    config.write_json(FILE, cleaned)
    config.audit(actor, "llm_settings.save", FILE, before=before, after=cleaned)
    return cleaned


def for_stage(key: str) -> dict[str, str]:
    """`complete()` keyword overrides for one stage: only the keys that are
    set, so an unset stage falls through to the environment exactly as before
    this module existed."""
    settings = load()
    entry = settings["stages"].get(key) or {}
    default = settings["default"]
    out: dict[str, str] = {}
    provider = entry.get("provider") or default.get("provider")
    model = entry.get("model") or default.get("model")
    if provider:
        out["provider"] = provider
    if model:
        out["model"] = model
    if key == "development-lane.reviewer" and not out:
        # The pre-existing environment override for an independent second
        # model keeps working when nothing is configured for the reviewer.
        if os.environ.get("REVIEW_LLM_PROVIDER"):
            out["provider"] = os.environ["REVIEW_LLM_PROVIDER"]
        if os.environ.get("REVIEW_LLM_MODEL"):
            out["model"] = os.environ["REVIEW_LLM_MODEL"]
    return out


def mode_override() -> str | None:
    """The configured LLM mode, or `None` to leave the environment in charge."""
    return load()["llm_mode"]


def _env_model(provider: str) -> str | None:
    return {
        "anthropic": os.environ.get("ANTHROPIC_MODEL"),
        "bedrock": os.environ.get("BEDROCK_MODEL"),
        "ollama": os.environ.get("OLLAMA_MODEL"),
        "custom": os.environ.get("CUSTOM_LLM_MODEL"),
        "claude_cli": os.environ.get("CLAUDE_CLI_MODEL"),
        "openai": os.environ.get("OPENAI_MODEL"),
    }.get(provider)


def provider_status() -> list[dict[str, Any]]:
    """Which providers are usable *now*, from the environment. Reports only
    whether a credential is present — never its value."""
    return [
        {"provider": "anthropic", "configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
         "needs": "ANTHROPIC_API_KEY", "env_model": _env_model("anthropic")},
        {"provider": "openai", "configured": bool(os.environ.get("OPENAI_API_KEY")),
         "needs": "OPENAI_API_KEY", "env_model": _env_model("openai")},
        {"provider": "bedrock",
         "configured": bool(os.environ.get("AWS_REGION") or os.environ.get("AWS_PROFILE")),
         "needs": "AWS_REGION / AWS_PROFILE", "env_model": _env_model("bedrock")},
        {"provider": "ollama", "configured": True,
         "needs": "OLLAMA_BASE_URL (defaults to localhost:11434)",
         "env_model": _env_model("ollama")},
        {"provider": "custom",
         "configured": bool(os.environ.get("CUSTOM_LLM_BASE_URL")
                            and os.environ.get("CUSTOM_LLM_MODEL")),
         "needs": "CUSTOM_LLM_BASE_URL + CUSTOM_LLM_MODEL", "env_model": _env_model("custom")},
        {"provider": "claude_cli", "configured": shutil.which("claude") is not None,
         "needs": "`claude` on PATH (record-time only)", "env_model": _env_model("claude_cli")},
    ]


def describe() -> dict[str, Any]:
    settings = load()
    return {
        "settings": settings,
        "stages": [{"key": k, "label": label, "group": group,
                    "effective": for_stage(k)} for k, label, group in STAGES],
        "providers": provider_status(),
        "environment": {
            "LLM_PROVIDER": os.environ.get("LLM_PROVIDER", "anthropic"),
            "LLM_MODE": os.environ.get("LLM_MODE", "replay"),
            "effective_mode": settings["llm_mode"] or os.environ.get("LLM_MODE", "replay"),
        },
        "providers_available": list(PROVIDERS),
        "modes": list(MODES),
    }
