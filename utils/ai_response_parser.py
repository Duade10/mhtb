from typing import List, Optional, Tuple

PROVIDER_LABEL_TO_CALLBACK = {
    "🤖 GPT": "accept_gpt",
    "🤖 Open AI": "accept_gpt",
    "🤖 OpenAI": "accept_gpt",
    "📝 Claude": "accept_claude",
    "🌍 Gemini": "accept_gemini",
    "✨ Other": "accept_other",
}


def _split_label_and_inline_content(text: str) -> Tuple[str, str]:
    """Split a provider line into the label and any inline content."""
    for separator in (":", "—"):
        if separator in text:
            label, rest = text.split(separator, 1)
            return label.strip(), rest.strip()
    return text.strip(), ""


PLACEHOLDER_CHARACTERS = {"—", "-", "–"}


def _has_meaningful_text(content: str) -> bool:
    """Check if the content represents an actual response and not a placeholder."""
    stripped = content.strip()
    if not stripped:
        return False

    def _remove_placeholder_characters(text: str) -> str:
        return "".join(ch for ch in text if ch not in PLACEHOLDER_CHARACTERS)

    without_placeholders = _remove_placeholder_characters(stripped).strip()
    return bool(without_placeholders)


def parse_ai_response_buttons(ai_response: str) -> List[Tuple[str, str]]:
    """Return button specs for providers that have a non-empty response."""
    buttons: List[Tuple[str, str]] = []
    if not ai_response:
        return buttons

    current_label: Optional[str] = None
    current_lines: List[str] = []

    def finalize_current() -> None:
        nonlocal current_label, current_lines
        if current_label is None:
            return

        content = "\n".join(line for line in current_lines if line is not None).strip()
        if _has_meaningful_text(content):
            callback = PROVIDER_LABEL_TO_CALLBACK.get(current_label)
            if callback:
                buttons.append((current_label, callback))

        current_label = None
        current_lines = []

    for raw_line in ai_response.splitlines():
        stripped_line = raw_line.strip()
        if stripped_line.startswith("- "):
            candidate_portion = stripped_line[2:].strip()
            candidate_label, inline_content = _split_label_and_inline_content(candidate_portion)
            normalized_label = candidate_label.rstrip(":").strip()

            if normalized_label in PROVIDER_LABEL_TO_CALLBACK:
                finalize_current()
                current_label = normalized_label
                current_lines = []
                inline_content = inline_content.strip()
                if inline_content:
                    current_lines.append(inline_content)
                continue

        if current_label is not None:
            if stripped_line:
                current_lines.append(stripped_line)

    finalize_current()
    return buttons
