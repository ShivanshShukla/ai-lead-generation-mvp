import re

PLACEHOLDER_SEND_ERROR = "Please replace placeholders before sending."

PLACEHOLDER_PATTERNS = (
    r"\[\s*(?:your name|company name|your name\s*/\s*ai sales assistant)\s*\]",
    r"\{\{[^}]*\}\}",
    r"<\s*your name\s*>",
)


def contains_blocked_placeholder(*values):
    combined_text = "\n".join(str(value or "") for value in values)

    return any(
        re.search(pattern, combined_text, flags=re.IGNORECASE)
        for pattern in PLACEHOLDER_PATTERNS
    )
