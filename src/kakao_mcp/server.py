#!/usr/bin/env python
"""MCP Server for KakaoTalk PC automation via Win32 API."""
import functools
import os
from typing import Dict, Optional

from mcp.server.fastmcp import FastMCP

from kakao_mcp import controller
from kakao_mcp import parser
from kakao_mcp import config
from kakao_mcp import aliases

INSTRUCTIONS = """\
카카오톡 PC를 Win32 API로 자동화하는 MCP 서버입니다(Windows + 카카오톡 PC 필요).

방 이름은 정확히 일치해야 합니다
- 방 이름을 받는 도구는 카카오톡 채팅방 창 제목과 글자 하나까지 같은 이름으로만 동작합니다.
  예: 실제 방 이름이 '학원홍길동선생님'이면 '홍길동'이나 '학원 홍길동'으로는 열리지 않습니다
  (아래 별칭 위키에 저장돼 있으면 열립니다).
- kakao_open_room은 검색 결과를 위에서부터 열어 보며 이름이 정확히 같은 방을 찾고,
  다른 방은 다시 닫습니다(원래 열려 있던 방은 닫지 않음). 이때 열어 본 방은 읽음 처리될 수 있습니다.
- 정확히 같은 방이 없으면 error와 함께 candidates(검색된 방들의 정확한 이름)를 돌려줍니다.
  이때 아무 방에나 보내지 말고, 사용자에게 "혹시 이 사람인가요?"라고 후보를 보여 주고 고르게 하세요.

별칭 위키
- 사용자가 부르는 이름 -> 정확한 방 이름을 저장하는 파일입니다:
  %USERPROFILE%\\Documents\\KakaoMCP_aliases.json (예: {"홍길동": "학원홍길동선생님"})
- 방 이름을 받는 모든 도구는 먼저 위키에서 이름을 찾아 정확한 방 이름으로 바꿔 씁니다.
  그래서 한 번 저장된 별칭은 그 뒤로 바로 쓸 수 있습니다.
- 사용자가 후보 중 하나를 고르면 kakao_open_room(room_name=<고른 방>, alias=<처음 말한 이름>)으로
  여세요. 방이 열리면 그 짝이 위키에 자동으로 저장되고, 결과에 alias_saved가 나옵니다.
- 파일을 직접 열어 별칭을 추가하거나 고쳐도 됩니다.

보내기 전 확인
- 보내기 도구(kakao_send_message, kakao_send_bulk, kakao_send_image, kakao_send_mention)는
  실제로 메시지를 보냅니다. 받는 방과 내용을 사용자가 정한 경우에만 쓰세요.
"""

WELCOME = """\
[처음 사용 안내 — 이 내용을 사용자에게 그대로 보여 주세요]
카카오톡 MCP가 연결됐습니다.
1. 방 이름은 카톡 채팅방 이름과 글자 하나까지 정확히 같아야 열리고 보낼 수 있습니다.
2. 정확히 같은 방이 없으면 비슷한 방들을 후보로 보여 드립니다. 골라 주시면 그 방으로 보냅니다.
3. 고르신 짝은 별칭 위키에 저장돼, 다음부터는 같은 이름으로 바로 보낼 수 있습니다.
   예: '홍길동' -> '학원홍길동선생님'
4. 별칭 위키 파일: {path}
   직접 열어 별칭을 추가하거나 고쳐도 됩니다.
5. 메시지는 받는 방과 내용을 정해 주셨을 때만 보냅니다.
"""

app = FastMCP(
    "kakao-mcp-server",
    instructions=INSTRUCTIONS,
)


def _tool():
    """app.tool() that adds the welcome note to the first result ever returned.

    "First" means the alias wiki file does not exist yet; it is created (empty)
    right after, so the note shows once per user.
    """
    def decorate(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)
            if not os.path.isfile(config.ALIASES_FILE) and isinstance(result, dict):
                aliases.save_all(aliases.load())
                result["first_run_notice"] = WELCOME.format(path=config.ALIASES_FILE)
            return result
        return app.tool()(wrapper)
    return decorate


@_tool()
def kakao_health_check() -> Dict:
    """Check if KakaoTalk PC is currently running.
    Returns status, window handle, and process ID."""
    try:
        status = controller.is_kakaotalk_running()
        if status["running"]:
            return {
                "message": "KakaoTalk is running",
                "running": True,
                "hwnd": status["hwnd"],
                "pid": status["pid"],
            }
        return {"message": "KakaoTalk is not running", "running": False}
    except Exception as e:
        return {"error": f"Health check failed: {e}"}


@_tool()
def kakao_list_open_rooms() -> Dict:
    """List all currently open KakaoTalk chat room windows.
    Returns a list of open chat rooms with their window titles."""
    try:
        status = controller.is_kakaotalk_running()
        if not status["running"]:
            return {"error": "KakaoTalk is not running"}
        rooms = controller.list_chat_windows()
        return {
            "message": f"Found {len(rooms)} open chat room(s)",
            "rooms": [{"title": r["title"], "hwnd": r["hwnd"]} for r in rooms],
        }
    except Exception as e:
        return {"error": f"Failed to list rooms: {e}"}


@_tool()
def kakao_open_room(room_name: str, alias: Optional[str] = None) -> Dict:
    """Open or bring to front a KakaoTalk chat room by name.
    The name is first looked up in the alias wiki (e.g. '홍길동' -> '학원홍길동선생님').
    If the chat window is already open, brings it to foreground.
    If not, searches for the room in KakaoTalk's search bar.
    If no result has exactly this name, returns "candidates": the exact names of
    the rooms the search found. Ask the user which one they meant, then call again
    with room_name=<their pick> and alias=<the name they originally said>.

    Args:
        room_name: The name of the chat room or person to open.
        alias: The name the user originally used for this room. When the room opens,
            alias -> room_name is saved to the alias wiki for next time.
    """
    try:
        room_name = aliases.resolve(room_name)
        hwnd = controller.find_chat_window(room_name)
        if hwnd:
            controller.bring_window_to_front(hwnd)
            reply = {"message": f"Chat room '{room_name}' brought to foreground", "hwnd": hwnd}
        else:
            result = controller.search_and_open_room(room_name)
            if not result["success"]:
                if result.get("candidates"):
                    return {"error": result["error"], "candidates": result["candidates"]}
                return {"error": result["error"]}
            reply = {"message": result["message"], "hwnd": result.get("hwnd")}
        reply["room_name"] = room_name
        if alias and alias != room_name:
            aliases.save(alias, room_name)
            reply["alias_saved"] = f"'{alias}' -> '{room_name}'"
        return reply
    except Exception as e:
        return {"error": f"Failed to open room '{room_name}': {e}"}


@_tool()
def kakao_send_message(room_name: str, message: str) -> Dict:
    """Send a text message to a KakaoTalk chat room.
    The chat room window must already be open.

    Args:
        room_name: Exact title of the chat room window.
        message: The text message to send.
    """
    try:
        room_name = aliases.resolve(room_name)
        if not message.strip():
            return {"error": "Message cannot be empty"}
        result = controller.send_message_to_room(room_name, message)
        if result["success"]:
            return {"message": result["message"]}
        return {"error": result["error"]}
    except Exception as e:
        return {"error": f"Failed to send message: {e}"}


@_tool()
def kakao_send_bulk(room_names: list[str], message: str, interval_sec: float = 0.5) -> Dict:
    """Send the same message to multiple KakaoTalk chat rooms at once.
    Opens each room if not already open and sends the message sequentially.
    Maintains a safe interval between rooms to ensure reliability.

    Args:
        room_names: List of chat room names or person names to send to.
        message: The text message to send to all rooms.
        interval_sec: Seconds to wait between rooms (default 0.5, minimum 0.3).
    """
    try:
        room_names = [aliases.resolve(n) for n in room_names]
        if not room_names:
            return {"error": "room_names cannot be empty"}
        if not message.strip():
            return {"error": "Message cannot be empty"}
        result = controller.send_bulk_messages(room_names, message, interval_sec)
        if result["success"]:
            return {"message": result["message"], "results": result["results"]}
        return {"error": result.get("message", "Failed to send bulk messages"), "results": result.get("results", [])}
    except Exception as e:
        return {"error": f"Failed to send bulk messages: {e}"}


@_tool()
def kakao_send_image(room_name: str, image_paths: list[str]) -> Dict:
    """Send image file(s) to a KakaoTalk chat room.
    Copies the image to clipboard using file-drop format and pastes into the chat.
    KakaoTalk shows a confirmation dialog which is automatically accepted.
    The chat room window must already be open.
    NOTE: This briefly brings the chat window to the foreground.

    Args:
        room_name: Exact title of the chat room window.
        image_paths: List of absolute file paths to images (JPG, PNG, GIF, BMP, WebP).
    """
    try:
        room_name = aliases.resolve(room_name)
        if not image_paths:
            return {"error": "image_paths cannot be empty"}

        for path in image_paths:
            if not os.path.isfile(os.path.abspath(path)):
                return {"error": f"Image file not found: {path}"}

        if len(image_paths) == 1:
            result = controller.send_image_to_room(room_name, image_paths[0])
            if result["success"]:
                return {"message": result["message"]}
            return {"error": result["error"]}
        else:
            result = controller.send_images_to_room(room_name, image_paths)
            if result["success"]:
                return {"message": result["message"], "results": result["results"]}
            return {"error": result.get("message", "Failed to send images"), "results": result.get("results", [])}
    except Exception as e:
        return {"error": f"Failed to send image: {e}"}


@_tool()
def kakao_read_messages(room_name: str, max_messages: int = 50) -> Dict:
    """Read recent messages from a KakaoTalk chat room.
    Uses clipboard-based reading (Ctrl+A, Ctrl+C on the chat list).
    NOTE: This briefly brings the chat window to the foreground.

    Args:
        room_name: Exact title of the chat room window.
        max_messages: Maximum number of recent messages to return (default 50).
    """
    try:
        room_name = aliases.resolve(room_name)
        result = controller.read_chat_messages(room_name)
        if not result["success"]:
            return {"error": result["error"]}
        parsed = parser.parse_chat_text(result["raw_text"])
        messages = parsed["messages"]
        if len(messages) > max_messages:
            messages = messages[-max_messages:]
        return {
            "message": f"Read {len(messages)} messages from '{room_name}'",
            "room_name": parsed["room_name"],
            "member_count": parsed["member_count"],
            "messages": messages,
        }
    except Exception as e:
        return {"error": f"Failed to read messages: {e}"}


@_tool()
def kakao_extract_links(room_name: str) -> Dict:
    """Extract all URLs/links from messages in a KakaoTalk chat room.
    Reads the chat first, then extracts URLs from all messages.

    Args:
        room_name: Exact title of the chat room window.
    """
    try:
        room_name = aliases.resolve(room_name)
        result = controller.read_chat_messages(room_name)
        if not result["success"]:
            return {"error": result["error"]}
        parsed = parser.parse_chat_text(result["raw_text"])
        urls = parser.extract_urls_from_messages(parsed["messages"])
        return {
            "message": f"Found {len(urls)} URL(s) in '{room_name}'",
            "links": urls,
        }
    except Exception as e:
        return {"error": f"Failed to extract links: {e}"}


@_tool()
def kakao_send_mention(room_name: str, mention_name: str, message: str) -> Dict:
    """Send a message with @mention to a KakaoTalk chat room.
    Types '@' to activate the mention popup, selects the target user,
    then sends the message. The chat room window must already be open.
    NOTE: This briefly brings the chat window to the foreground.

    Args:
        room_name: Exact title of the chat room window.
        mention_name: Display name of the person to mention (e.g. '홍길동').
        message: The text message to send after the mention.
    """
    try:
        room_name = aliases.resolve(room_name)
        if not mention_name.strip():
            return {"error": "Mention name cannot be empty"}
        if not message.strip():
            return {"error": "Message cannot be empty"}
        result = controller.send_mention_message(room_name, mention_name, message)
        if result["success"]:
            return {"message": result["message"]}
        return {"error": result["error"]}
    except Exception as e:
        return {"error": f"Failed to send mention message: {e}"}


@_tool()
def kakao_download_images(
    room_name: str,
    output_dir: Optional[str] = None,
    max_images: int = 10,
) -> Dict:
    """Download recent images from KakaoTalk's local cache.
    Images are sorted by modification time (newest first).
    Note: Cache is global, not per-room — images are the most recently cached ones.

    Args:
        room_name: Chat room name (for context/logging).
        output_dir: Directory to save images. Defaults to Documents/KakaoMCP_Images.
        max_images: Maximum number of images to download (default 10).
    """
    try:
        if output_dir is None:
            output_dir = config.DEFAULT_IMAGE_OUTPUT_DIR
        os.makedirs(output_dir, exist_ok=True)
        result = controller.download_recent_images(room_name, output_dir, max_images)
        return result
    except Exception as e:
        return {"error": f"Failed to download images: {e}"}


@_tool()
def kakao_start_monitor(
    room_name: str,
    keywords: list[str],
    poll_interval_sec: float = 5.0,
) -> Dict:
    """Start monitoring a KakaoTalk chat room for keyword matches.
    Runs in background, checking for new messages at the specified interval.
    Use kakao_get_monitor_events() to retrieve detected keyword matches.
    NOTE: The chat room window must be open. Polling brings it to foreground briefly.

    Args:
        room_name: Exact title of the chat room window to monitor.
        keywords: List of keywords to watch for (case-insensitive).
        poll_interval_sec: Seconds between each poll (minimum 3, default 5).
    """
    try:
        room_name = aliases.resolve(room_name)
        if not keywords:
            return {"error": "Keywords list cannot be empty"}
        result = controller._chat_monitor.start(room_name, keywords, poll_interval_sec)
        if result["success"]:
            return {"message": result["message"]}
        return {"error": result["error"]}
    except Exception as e:
        return {"error": f"Failed to start monitor: {e}"}


@_tool()
def kakao_stop_monitor() -> Dict:
    """Stop the running chat room monitor."""
    try:
        result = controller._chat_monitor.stop()
        if result["success"]:
            return {"message": result["message"]}
        return {"error": result["error"]}
    except Exception as e:
        return {"error": f"Failed to stop monitor: {e}"}


@_tool()
def kakao_get_monitor_events() -> Dict:
    """Get pending keyword match events from the chat monitor.
    Returns events detected since last call. Each event includes:
    - keyword: the matched keyword
    - trigger_message: the message that matched (sender, time, text)
    - recent_context: last 10 messages for context understanding
    - room_name: the monitored chat room

    Call this periodically while monitor is running to check for matches.
    """
    try:
        is_running = controller._chat_monitor.is_running
        events = controller._chat_monitor.get_events()
        return {
            "monitoring": is_running,
            "event_count": len(events),
            "events": events,
        }
    except Exception as e:
        return {"error": f"Failed to get monitor events: {e}"}


def main():
    app.run(transport="stdio")


if __name__ == "__main__":
    main()
