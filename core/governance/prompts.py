"""Prompt registry and versioning for model governance.

Every prompt used by agents is versioned and locked. When the LLM model
version changes, the entire eval suite must re-run to catch regressions.

This prevents silent degradation: a prompt A might be calibrated for Gemini 2.0
but produce worse results on Gemini 2.1 without us noticing.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class PromptVersion:
    """A single versioned prompt."""

    name: str  # e.g., "phase_01_surveillance", "aoc_gdp_responder"
    text: str  # the full prompt text
    version: str  # semantic version (e.g., "1.0.0")
    model: str  # model used when this prompt was created (e.g., "gemini-2.0-flash")
    created_at: str  # ISO timestamp
    checksum: str = field(default="")  # SHA256 of the prompt text

    def __post_init__(self):
        """Compute checksum if not provided."""
        if not self.checksum:
            self.checksum = hashlib.sha256(self.text.encode()).hexdigest()


@dataclass
class PromptLockfile:
    """A locked set of prompts for a specific model version.

    Used for audit trail: "scenario X ran with lockfile v2 (model gemini-2.0)".
    If the model upgrades to gemini-2.1, a new lockfile is created and evals
    re-run against all prompts to catch regressions.
    """

    model: str  # e.g., "gemini-2.0-flash"
    model_version: str  # e.g., "2.0"
    lockfile_version: str  # e.g., "1.0.0" — bumped when any prompt changes
    created_at: str
    prompts: Dict[str, PromptVersion] = field(default_factory=dict)
    eval_pass_rate: Optional[float] = None  # frozen baseline for this lockfile
    eval_test_count: Optional[int] = None
    checksum: str = field(default="")

    def __post_init__(self):
        """Compute lockfile checksum."""
        if not self.checksum:
            prompt_hashes = sorted(
                [f"{k}:{v.checksum}" for k, v in self.prompts.items()]
            )
            content = json.dumps(prompt_hashes)
            self.checksum = hashlib.sha256(content.encode()).hexdigest()

    def add_prompt(self, name: str, text: str, version: str):
        """Register a prompt in this lockfile."""
        pv = PromptVersion(
            name=name,
            text=text,
            version=version,
            model=self.model,
            created_at=datetime.utcnow().isoformat(),
        )
        self.prompts[name] = pv

    def serialize(self) -> str:
        """Export to JSON for storage."""
        return json.dumps(
            {
                "model": self.model,
                "model_version": self.model_version,
                "lockfile_version": self.lockfile_version,
                "created_at": self.created_at,
                "checksum": self.checksum,
                "eval_pass_rate": self.eval_pass_rate,
                "eval_test_count": self.eval_test_count,
                "prompts": {
                    name: {
                        "name": pv.name,
                        "text": pv.text,
                        "version": pv.version,
                        "checksum": pv.checksum,
                    }
                    for name, pv in self.prompts.items()
                },
            },
            indent=2,
        )

    @classmethod
    def deserialize(cls, json_str: str) -> "PromptLockfile":
        """Load from JSON."""
        data = json.loads(json_str)
        lockfile = cls(
            model=data["model"],
            model_version=data["model_version"],
            lockfile_version=data["lockfile_version"],
            created_at=data["created_at"],
            eval_pass_rate=data.get("eval_pass_rate"),
            eval_test_count=data.get("eval_test_count"),
            checksum=data.get("checksum", ""),
        )
        for name, pv_data in data.get("prompts", {}).items():
            lockfile.prompts[name] = PromptVersion(
                name=pv_data["name"],
                text=pv_data["text"],
                version=pv_data["version"],
                model=lockfile.model,
                created_at=pv_data.get("created_at", datetime.utcnow().isoformat()),
                checksum=pv_data.get("checksum", ""),
            )
        return lockfile


# Global registry (singleton)
_LOCKFILE: Optional[PromptLockfile] = None


def init_lockfile(model: str, model_version: str, lockfile_version: str):
    """Initialize a new prompt lockfile."""
    global _LOCKFILE
    _LOCKFILE = PromptLockfile(
        model=model,
        model_version=model_version,
        lockfile_version=lockfile_version,
        created_at=datetime.utcnow().isoformat(),
    )


def register_prompt(name: str, text: str, version: str = "1.0.0"):
    """Register a prompt in the global lockfile."""
    if _LOCKFILE is None:
        raise RuntimeError("Lockfile not initialized; call init_lockfile() first")
    _LOCKFILE.add_prompt(name, text, version)


def get_prompt(name: str) -> str:
    """Retrieve a prompt by name from the global lockfile."""
    if _LOCKFILE is None:
        raise RuntimeError("Lockfile not initialized; call init_lockfile() first")
    if name not in _LOCKFILE.prompts:
        raise KeyError(f"Prompt '{name}' not registered in lockfile")
    return _LOCKFILE.prompts[name].text


def get_lockfile() -> Optional[PromptLockfile]:
    """Retrieve the current lockfile (e.g., for audit trails)."""
    return _LOCKFILE


def set_eval_baseline(pass_rate: float, test_count: int):
    """Lock in the eval baseline for this lockfile version."""
    if _LOCKFILE is None:
        raise RuntimeError("Lockfile not initialized")
    _LOCKFILE.eval_pass_rate = pass_rate
    _LOCKFILE.eval_test_count = test_count
