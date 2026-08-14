import re
from pathlib import Path


def test_dashboard_fetches_snapshot_only_on_reconnect() -> None:
    app_js_path = Path(__file__).parent.parent / "telemetry_gateway" / "static" / "app.js"
    content = app_js_path.read_text()
    
    assert re.search(r"let\s+hasConnected\s*=\s*false", content), "app.js must define hasConnected"
    
    # Extract the socket.addEventListener('open', ...) block
    match = re.search(r"socket\.addEventListener\('open',\s*\(\)\s*=>\s*\{(.*?)\}\);", content, re.DOTALL)
    assert match is not None, "Could not find socket.addEventListener('open', ...) in app.js"
    
    open_block = match.group(1)
    
    if_match = re.search(r"if\s*\(\s*hasConnected\s*\)\s*\{([^}]*)\}", open_block, re.DOTALL)
    assert if_match is not None, "open event must contain if (hasConnected) condition"
    
    if_block = if_match.group(1)
    assert "loadSnapshot(" in if_block, "loadSnapshot() must be called inside the if (hasConnected) condition"
    
    end_of_if = if_match.end()
    rest_of_open_block = open_block[end_of_if:]
    assert re.search(r"hasConnected\s*=\s*true", rest_of_open_block), (
        "hasConnected must be set to true after checking the condition"
    )

