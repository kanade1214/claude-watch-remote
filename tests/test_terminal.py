import asyncio

import pytest

from app.errors import RelayError
from app.terminal import MAX_PROMPT_LENGTH, validate_prompt_text


def test_validate_prompt_text_accepts_normal_text():
    validate_prompt_text("テストを実行して")


def test_validate_prompt_text_rejects_too_long():
    with pytest.raises(RelayError) as exc_info:
        validate_prompt_text("a" * (MAX_PROMPT_LENGTH + 1))
    assert exc_info.value.code == "PROMPT_TOO_LONG"


def test_validate_prompt_text_rejects_nul_byte():
    with pytest.raises(RelayError) as exc_info:
        validate_prompt_text("hello\x00world")
    assert exc_info.value.code == "INVALID_MESSAGE"


def test_validate_prompt_text_allows_newlines():
    validate_prompt_text("line one\nline two")


def test_tmux_adapter_reports_not_alive_when_tmux_missing():
    from app.terminal import TmuxTerminalAdapter

    adapter = TmuxTerminalAdapter(session_name="claude-remote-does-not-exist")
    assert asyncio.run(adapter.is_alive()) is False
