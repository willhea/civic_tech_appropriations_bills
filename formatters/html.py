"""Generate a standalone HTML report from a bill diff dict."""

import difflib
from html import escape


def word_diff(old_text: str, new_text: str, threshold: float = 0.4) -> str | None:
    """Produce an inline HTML diff at the word level.

    Returns an HTML string with <del> and <ins> tags wrapping changed words,
    or None if the texts are too dissimilar (below *threshold*).
    """
    old_words = old_text.split()
    new_words = new_text.split()

    matcher = difflib.SequenceMatcher(None, old_words, new_words)
    if matcher.ratio() < threshold:
        return None

    parts: list[str] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            parts.append(escape(" ".join(old_words[i1:i2])))
        elif op == "replace":
            parts.append("<del>" + escape(" ".join(old_words[i1:i2])) + "</del>")
            parts.append("<ins>" + escape(" ".join(new_words[j1:j2])) + "</ins>")
        elif op == "delete":
            parts.append("<del>" + escape(" ".join(old_words[i1:i2])) + "</del>")
        elif op == "insert":
            parts.append("<ins>" + escape(" ".join(new_words[j1:j2])) + "</ins>")

    return " ".join(parts)
