"""Provisional knowledge base loader. Replaced by the KB tables once E0-03 lands."""

from __future__ import annotations

from pathlib import Path

import yaml

from .schemas import KnowledgeBase


def load_kb(path: Path) -> KnowledgeBase:
    with Path(path).open(encoding="utf-8") as f:
        return KnowledgeBase.model_validate(yaml.safe_load(f))
