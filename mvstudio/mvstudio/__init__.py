"""mvstudio — local-first, beat-synced music video engine (Phase 0 MVP).

Pipeline: audio analysis (librosa) -> storyboard JSON (rule-based or LLM
director) -> deterministic FFmpeg render. The storyboard JSON is the
product's core contract: every renderer/UI/MCP surface reads only that.
"""

__version__ = "0.1.0"
