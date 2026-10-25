"""Item name normalization and alias resolution."""

import re

ALIASES = {
    "calc textbook": "calculus textbook",
    "calc book": "calculus textbook",
    "calculus book": "calculus textbook",
    "fridge": "mini-fridge",
    "mini fridge": "mini-fridge",
    "minifridge": "mini-fridge",
    "bicycle lock": "bike lock",
    "u-lock": "bike lock",
    "desk light": "desk lamp",
}

_SS_ENDINGS = ("ss", "us", "is")


def _singularize_word(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("sses", "xes", "ches", "shes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith(_SS_ENDINGS):
        return word[:-1]
    return word


def normalize(name: str) -> str:
    """Lowercase, trim, collapse spaces and singularize the last word."""
    words = re.sub(r"\s+", " ", name.strip().lower()).split(" ")
    words[-1] = _singularize_word(words[-1])
    return " ".join(words).strip()


def canonicalize(name: str) -> str:
    normalized = normalize(name)
    return ALIASES.get(normalized, normalized)


def is_match(have_name: str, need_name: str) -> bool:
    canonical = canonicalize(have_name)
    return bool(canonical) and canonical == canonicalize(need_name)
