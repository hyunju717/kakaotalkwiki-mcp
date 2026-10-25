"""Tests for the alias wiki and its use in kakao_open_room."""
import sys
import os
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from kakao_mcp import aliases, config, server


@pytest.fixture(autouse=True)
def alias_file(tmp_path, monkeypatch):
    path = tmp_path / "aliases.json"
    monkeypatch.setattr(config, "ALIASES_FILE", str(path))
    return path


def test_resolve_without_file_returns_name():
    assert aliases.resolve("홍길동") == "홍길동"


def test_save_then_resolve():
    aliases.save("홍길동", "학원홍길동선생님")
    aliases.save("김철수", "김철수❤️")
    assert aliases.resolve("홍길동") == "학원홍길동선생님"
    assert aliases.resolve("김철수") == "김철수❤️"
    assert aliases.resolve("이영희") == "이영희"


@patch("kakao_mcp.server.controller")
def test_open_room_uses_alias(mock_ctrl):
    aliases.save("홍길동", "학원홍길동선생님")
    mock_ctrl.find_chat_window.return_value = 111
    result = server.kakao_open_room("홍길동")
    mock_ctrl.find_chat_window.assert_called_once_with("학원홍길동선생님")
    assert result["room_name"] == "학원홍길동선생님"


@patch("kakao_mcp.server.controller")
def test_open_room_returns_candidates_without_saving(mock_ctrl):
    mock_ctrl.find_chat_window.return_value = None
    mock_ctrl.search_and_open_room.return_value = {
        "success": False, "error": "not found",
        "candidates": ["학원홍길동선생님", "동창모임"],
    }
    result = server.kakao_open_room("학원홍길동", alias="홍길동")
    assert result["candidates"] == ["학원홍길동선생님", "동창모임"]
    assert aliases.load() == {}


@patch("kakao_mcp.server.controller")
def test_open_room_saves_picked_candidate(mock_ctrl):
    mock_ctrl.find_chat_window.return_value = None
    mock_ctrl.search_and_open_room.return_value = {
        "success": True, "message": "Opened", "hwnd": 222,
    }
    result = server.kakao_open_room("학원홍길동선생님", alias="학원홍길동")
    assert aliases.load() == {"학원홍길동": "학원홍길동선생님"}
    assert "alias_saved" in result
    assert server.kakao_open_room("학원홍길동")["room_name"] == "학원홍길동선생님"


@patch("kakao_mcp.server.controller")
def test_send_message_uses_alias(mock_ctrl):
    aliases.save("홍길동", "학원홍길동선생님")
    mock_ctrl.send_message_to_room.return_value = {"success": True, "message": "sent"}
    server.kakao_send_message("홍길동", "윈도우도 된다")
    mock_ctrl.send_message_to_room.assert_called_once_with("학원홍길동선생님", "윈도우도 된다")


@patch("kakao_mcp.server.controller")
def test_welcome_note_only_on_first_use(mock_ctrl, alias_file):
    mock_ctrl.is_kakaotalk_running.return_value = {"running": False}
    first = server.kakao_health_check()
    assert "first_run_notice" in first
    assert str(alias_file) in first["first_run_notice"]
    assert alias_file.exists() and aliases.load() == {}
    assert "first_run_notice" not in server.kakao_health_check()


@patch("kakao_mcp.server.controller")
def test_no_welcome_when_wiki_exists(mock_ctrl):
    aliases.save("홍길동", "학원홍길동선생님")
    mock_ctrl.is_kakaotalk_running.return_value = {"running": False}
    assert "first_run_notice" not in server.kakao_health_check()
