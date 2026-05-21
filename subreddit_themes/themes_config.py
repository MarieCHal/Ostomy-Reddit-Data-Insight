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
    max_keywords_in_hypothesis: int = 10
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


def build_nli_hypothesis(category: ThemeCategory, config: ThemesConfig) -> str:
    """Hypothesis string sent to BART-MNLI (optionally enriched with keywords)."""
    base = category.hypothesis.strip()
    if not config.enrich_hypothesis_with_keywords or not category.keywords:
        return base
    kws = category.keywords[: config.max_keywords_in_hypothesis]
    suffix = " Related topics: " + ", ".join(kws) + "."
    # Keep within a reasonable length for the tokenizer (~512 tokens total with post).
    max_len = 480
    if len(base) + len(suffix) > max_len:
        suffix = " Related topics: " + ", ".join(kws[:6]) + "."
    if len(base) + len(suffix) > max_len:
        return base[:max_len]
    return base + suffix


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
        max_keywords_in_hypothesis=int(cfg.get("max_keywords_in_hypothesis", 10)),
        keyword_boost_per_match=float(cfg.get("keyword_boost_per_match", 0.03)),
        keyword_boost_cap=float(cfg.get("keyword_boost_cap", 0.12)),
        exclusion_penalty=float(cfg.get("exclusion_penalty", 0.35)),
    )
