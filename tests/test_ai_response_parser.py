from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from utils.ai_response_parser import parse_ai_response_buttons


def test_parse_ai_response_buttons_skips_placeholder_sections():
    ai_response = (
        "- 🤖 GPT\n"
        "Great response here.\n"
        "- 📝 Claude\n"
        "—\n"
        "- 🌍 Gemini\n"
        "Another solid reply.\n"
        "- ✨ Other\n"
        "\n"
    )

    buttons = parse_ai_response_buttons(ai_response)

    assert buttons == [
        ("🤖 GPT", "accept_gpt"),
        ("🌍 Gemini", "accept_gemini"),
    ]


def test_parse_ai_response_buttons_handles_inline_content_and_aliases():
    ai_response = (
        "- 🤖 Open AI: Hello there!\n"
        "- 📝 Claude: —\n"
        "- 🌍 Gemini:   \n"
        "- ✨ Other: Custom reply\n"
    )

    buttons = parse_ai_response_buttons(ai_response)

    assert buttons == [
        ("🤖 Open AI", "accept_gpt"),
        ("✨ Other", "accept_other"),
    ]


def test_parse_ai_response_buttons_ignores_plain_hyphen_placeholders():
    ai_response = (
        "- 🤖 GPT\n"
        "------\n"
        "- 📝 Claude\n"
        "Actual response\n"
    )

    buttons = parse_ai_response_buttons(ai_response)

    assert buttons == [
        ("📝 Claude", "accept_claude"),
    ]
