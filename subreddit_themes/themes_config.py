"""Load taxonomy YAML for BART-MNLI multi-label classification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ThemeCategory:
    id: str
    short_name: str
    hypothesis: str
    display_name: str = ""
    definition: str = ""
    keywords: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    exclusion_signals: tuple[str, ...] = ()


@dataclass(frozen=True)
class ThemesConfig:
    categories: list[ThemeCategory]
    threshold: float
    max_text_chars: int
    hypothesis_template: str
    classification_mode: str
    version: int
    enrich_hypothesis_with_keywords: bool = True
    enrich_hypothesis_with_definition: bool = False
    enrich_hypothesis_with_examples: bool = False
    max_keywords_in_hypothesis: int = 10
    max_examples_in_hypothesis: int = 5
    max_hypothesis_chars: int = 600
    keyword_boost_per_match: float = 0.03
    keyword_boost_cap: float = 0.12
    exclusion_penalty: float = 0.35

    @property
    def short_names(self) -> list[str]:
        return [c.short_name for c in self.categories]


def _str_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(x).strip() for x in value if str(x).strip())


def _truncate_hypothesis(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    trimmed = text[: max_len - 3].rsplit(" ", 1)[0]
    return trimmed + "..."


def build_nli_hypothesis(category: ThemeCategory, config: ThemesConfig) -> str:
    """Hypothesis string sent to BART-MNLI (enriched per config flags)."""
    parts = [category.hypothesis.strip()]

    if config.enrich_hypothesis_with_definition and category.definition:
        parts.append(category.definition.strip())

    if config.enrich_hypothesis_with_examples and category.examples:
        picked = category.examples[: config.max_examples_in_hypothesis]
        quoted = "; ".join(f'"{ex}"' for ex in picked)
        parts.append(f"Example posts: {quoted}.")

    if config.enrich_hypothesis_with_keywords and category.keywords:
        kws = category.keywords[: config.max_keywords_in_hypothesis]
        parts.append("Related topics: " + ", ".join(kws) + ".")

    return _truncate_hypothesis(" ".join(parts), config.max_hypothesis_chars)


def keyword_matches(text: str, keywords: tuple[str, ...]) -> int:
    lower = text.lower()
    return sum(1 for kw in keywords if kw.lower() in lower)


def apply_keyword_boost(
    text: str,
    theme_scores: dict[str, float],
    categories: list[ThemeCategory],
    config: ThemesConfig,
) -> dict[str, float]:
    if config.keyword_boost_per_match <= 0:
        return theme_scores
    boosted = dict(theme_scores)
    for cat in categories:
        if not cat.keywords:
            continue
        n = keyword_matches(text, cat.keywords)
        if n:
            boost = min(config.keyword_boost_cap, n * config.keyword_boost_per_match)
            boosted[cat.short_name] = min(1.0, boosted.get(cat.short_name, 0.0) + boost)
    return boosted


def apply_exclusion_penalty(
    text: str,
    theme_scores: dict[str, float],
    categories: list[ThemeCategory],
    config: ThemesConfig,
) -> dict[str, float]:
    """Lower digestive_relevance when exclusion signals appear (F0)."""
    if config.exclusion_penalty <= 0:
        return theme_scores
    adjusted = dict(theme_scores)
    for cat in categories:
        if not cat.exclusion_signals:
            continue
        if keyword_matches(text, cat.exclusion_signals):
            adjusted[cat.short_name] = max(
                0.0, adjusted.get(cat.short_name, 0.0) - config.exclusion_penalty
            )
    return adjusted


def load_themes_config(path: Path) -> ThemesConfig:
    with open(path, encoding="utf-8") as f:
        cfg: dict[str, Any] = yaml.safe_load(f) or {}

    raw_categories = cfg.get("categories")
    if not isinstance(raw_categories, list) or not raw_categories:
        raise ValueError(f"Invalid themes file (missing 'categories'): {path}")

    categories: list[ThemeCategory] = []
    seen_names: set[str] = set()
    for item in raw_categories:
        if not isinstance(item, dict):
            raise ValueError("'categories' entries must be mappings")
        cat_id = str(item.get("id", "")).strip()
        short_name = str(item.get("short_name", "")).strip()
        hypothesis = str(
            item.get("hypothesis") or item.get("hypothesis_template") or ""
        ).strip()
        if not cat_id or not short_name or not hypothesis:
            raise ValueError(
                f"Each category needs id, short_name, hypothesis: {item!r}"
            )
        if short_name in seen_names:
            raise ValueError(f"Duplicate short_name: {short_name!r}")
        seen_names.add(short_name)
        categories.append(
            ThemeCategory(
                id=cat_id,
                short_name=short_name,
                hypothesis=hypothesis,
                display_name=str(item.get("display_name", "")).strip(),
                definition=str(item.get("definition", "")).strip(),
                keywords=_str_list(item.get("keywords")),
                examples=_str_list(item.get("examples") or item.get("examples_positive")),
                exclusion_signals=_str_list(item.get("exclusion_signals")),
            )
        )

    threshold = float(cfg.get("threshold", 0.40))
    max_text_chars = int(cfg.get("max_text_chars", 1000))
    hypothesis_template = str(cfg.get("hypothesis_template") or "{}")
    classification_mode = str(cfg.get("classification_mode") or "multi_label")
    version = int(cfg.get("version", 2))

    return ThemesConfig(
        categories=categories,
        threshold=threshold,
        max_text_chars=max_text_chars,
        hypothesis_template=hypothesis_template,
        classification_mode=classification_mode,
        version=version,
        enrich_hypothesis_with_keywords=bool(cfg.get("enrich_hypothesis_with_keywords", True)),
        enrich_hypothesis_with_definition=bool(
            cfg.get("enrich_hypothesis_with_definition", False)
        ),
        enrich_hypothesis_with_examples=bool(
            cfg.get("enrich_hypothesis_with_examples", False)
        ),
        max_keywords_in_hypothesis=int(cfg.get("max_keywords_in_hypothesis", 10)),
        max_examples_in_hypothesis=int(cfg.get("max_examples_in_hypothesis", 5)),
        max_hypothesis_chars=int(cfg.get("max_hypothesis_chars", 600)),
        keyword_boost_per_match=float(cfg.get("keyword_boost_per_match", 0.03)),
        keyword_boost_cap=float(cfg.get("keyword_boost_cap", 0.12)),
        exclusion_penalty=float(cfg.get("exclusion_penalty", 0.35)),
    )
