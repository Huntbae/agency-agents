"""comfyui-mvstudio: mvstudio music video engine as ComfyUI nodes.

Install (symlink this folder into ComfyUI):
  ln -s ~/agency-agents/mvstudio/comfyui-mvstudio ~/ComfyUI/custom_nodes/comfyui-mvstudio
"""

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
