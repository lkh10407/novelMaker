"""Tests for novel_maker.utils."""

import pytest

from novel_maker.utils import parse_json_response


class TestParseJsonResponse:
    def test_plain_json_object(self):
        assert parse_json_response('{"key": "value"}') == {"key": "value"}

    def test_plain_json_array(self):
        assert parse_json_response("[1, 2, 3]") == [1, 2, 3]

    def test_json_with_whitespace(self):
        assert parse_json_response('  \n {"a": 1} \n  ') == {"a": 1}

    def test_json_in_markdown_code_fence(self):
        raw = '```json\n{"key": "value"}\n```'
        assert parse_json_response(raw) == {"key": "value"}

    def test_json_in_plain_code_fence(self):
        raw = "```\n[1, 2]\n```"
        assert parse_json_response(raw) == [1, 2]

    def test_json_with_surrounding_text(self):
        raw = 'Here is the result:\n```json\n{"ok": true}\n```\nDone.'
        assert parse_json_response(raw) == {"ok": True}

    def test_nested_json(self):
        raw = '{"a": {"b": [1, 2]}, "c": "d"}'
        result = parse_json_response(raw)
        assert result == {"a": {"b": [1, 2]}, "c": "d"}

    def test_invalid_json_raises(self):
        with pytest.raises(Exception):
            parse_json_response("not json at all")

    def test_empty_string_raises(self):
        with pytest.raises(Exception):
            parse_json_response("")
