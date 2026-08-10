"""Tests for the Stop hook's transcript parsing.

The hook scripts are stdlib-only standalone files rather than a package (they
run under whatever interpreter Claude Code invokes them with), so the
directory goes on sys.path to import one.
"""
import json
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent / "claude-hooks"
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

import stop  # noqa: E402


def write_transcript(tmp_path, entries) -> str:
    path = tmp_path / "transcript.jsonl"
    path.write_text(
        "\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries) + "\n",
        encoding="utf-8",
    )
    return str(path)


def assistant(*blocks, sidechain: bool = False) -> dict:
    return {
        "type": "assistant",
        "isSidechain": sidechain,
        "message": {"role": "assistant", "content": list(blocks)},
    }


def text_block(text: str) -> dict:
    return {"type": "text", "text": text}


def test_extracts_newest_assistant_text(tmp_path):
    path = write_transcript(
        tmp_path,
        [
            assistant(text_block("古い応答")),
            {"type": "user", "message": {"role": "user", "content": "次の質問"}},
            assistant(text_block("新しい応答")),
        ],
    )
    assert stop.extract_last_assistant_text(path) == "新しい応答"


def test_joins_multiple_text_blocks_and_drops_tool_use(tmp_path):
    path = write_transcript(
        tmp_path,
        [
            assistant(
                text_block("まず確認します。"),
                {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
                text_block("以上です。"),
            )
        ],
    )
    assert stop.extract_last_assistant_text(path) == "まず確認します。\n以上です。"


def test_walks_past_a_tool_use_only_turn(tmp_path):
    """A trailing turn that only issued tool calls has nothing to show."""
    path = write_transcript(
        tmp_path,
        [
            assistant(text_block("答えはこれです。")),
            assistant({"type": "tool_use", "name": "Read", "input": {}}),
        ],
    )
    assert stop.extract_last_assistant_text(path) == "答えはこれです。"


def test_skips_sidechain_subagent_output(tmp_path):
    path = write_transcript(
        tmp_path,
        [
            assistant(text_block("メインの応答")),
            assistant(text_block("サブエージェントの応答"), sidechain=True),
        ],
    )
    assert stop.extract_last_assistant_text(path) == "メインの応答"


def test_tolerates_a_corrupt_line(tmp_path):
    path = tmp_path / "transcript.jsonl"
    path.write_text(
        json.dumps(assistant(text_block("有効な応答")), ensure_ascii=False) + "\n{ not json\n",
        encoding="utf-8",
    )
    assert stop.extract_last_assistant_text(str(path)) == "有効な応答"


def test_plain_string_content(tmp_path):
    path = write_transcript(
        tmp_path,
        [{"type": "assistant", "message": {"role": "assistant", "content": "素の文字列"}}],
    )
    assert stop.extract_last_assistant_text(path) == "素の文字列"


def test_missing_transcript_returns_empty(tmp_path):
    assert stop.extract_last_assistant_text(str(tmp_path / "nope.jsonl")) == ""


def test_transcript_without_assistant_entries_returns_empty(tmp_path):
    path = write_transcript(tmp_path, [{"type": "user", "message": {"role": "user", "content": "hi"}}])
    assert stop.extract_last_assistant_text(path) == ""


def test_reads_only_the_tail_of_a_huge_transcript(tmp_path, monkeypatch):
    """The partial first line of a tail read must not break parsing."""
    monkeypatch.setattr(stop, "TAIL_BYTES", 200)
    path = write_transcript(
        tmp_path,
        [
            assistant(text_block("x" * 500)),
            assistant(text_block("最後の短い応答")),
        ],
    )
    assert stop.extract_last_assistant_text(path) == "最後の短い応答"
