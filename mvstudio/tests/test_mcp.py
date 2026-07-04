"""MCP server e2e: drive the real stdio transport with raw JSON-RPC,
exactly as an MCP client (Claude Desktop/Code) would."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

pytest.importorskip("mcp", reason="mcp SDK not installed (pip install 'mvstudio[mcp]')")


class StdioClient:
    def __init__(self):
        env = dict(os.environ, PYTHONPATH=ROOT)
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "mvstudio.mcp_server"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, env=env, cwd=ROOT)
        self._q: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        self._id = 0

    def _pump(self):
        for line in self.proc.stdout:
            self._q.put(line)

    def notify(self, method: str, params: dict | None = None):
        msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def request(self, method: str, params: dict | None = None,
                timeout: float = 120.0) -> dict:
        self._id += 1
        msg = {"jsonrpc": "2.0", "id": self._id, "method": method,
               "params": params or {}}
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        while True:
            data = json.loads(self._q.get(timeout=timeout))
            if data.get("id") == self._id:
                assert "error" not in data, data["error"]
                return data["result"]

    def close(self):
        self.proc.terminate()
        self.proc.wait(timeout=10)


@pytest.fixture(scope="module")
def client():
    c = StdioClient()
    init = c.request("initialize", {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "mvstudio-test", "version": "0"},
    })
    assert init["serverInfo"]["name"] == "mvstudio"
    c.notify("notifications/initialized")
    yield c
    c.close()


@pytest.fixture(scope="module")
def assets(tmp_path_factory):
    root = tmp_path_factory.mktemp("mcp_assets")
    sys.path.insert(0, os.path.join(ROOT, "examples"))
    import make_demo_assets as demo
    song, images = str(root / "demo.wav"), str(root / "images")
    demo.make_song(song)
    demo.make_images(images)
    return song, images


def _call(client: StdioClient, name: str, args: dict) -> dict:
    result = client.request("tools/call", {"name": name, "arguments": args})
    assert not result.get("isError"), result
    return json.loads(result["content"][0]["text"])


def test_tools_listed(client):
    tools = {t["name"] for t in client.request("tools/list")["tools"]}
    assert {"analyze_song", "generate_storyboard", "render_video",
            "make_music_video", "list_camera_presets",
            "inspect_storyboard"} <= tools


def test_analyze_and_presets(client, assets):
    song, _ = assets
    analysis = _call(client, "analyze_song", {"song_path": song})
    assert 100 <= analysis["bpm"] <= 140
    presets = client.request("tools/call",
                             {"name": "list_camera_presets", "arguments": {}})
    assert not presets.get("isError")


def test_full_pipeline_over_mcp(client, assets, tmp_path_factory):
    song, images = assets
    out = str(tmp_path_factory.mktemp("mcp_out") / "mv.mp4")
    result = _call(client, "make_music_video", {
        "song_path": song, "images_dir": images, "output_path": out,
        "width": 640, "height": 360, "fps": 24, "seed": 7,
    })
    assert result["cut_count"] > 3
    assert os.path.getsize(result["output_path"]) > 50_000

    sb_path = os.path.splitext(out)[0] + ".storyboard.json"
    info = _call(client, "inspect_storyboard", {"storyboard_path": sb_path})
    assert info["valid"] and info["cut_count"] == result["cut_count"]
