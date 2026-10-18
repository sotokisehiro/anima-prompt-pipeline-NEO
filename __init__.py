"""ComfyUI カスタムノードの入口。Forge / CLI / Web はこのファイルを読まない。

ここでは重い import をしない(service などはノードの実行時に遅延 import する)。
"""
from .comfyui.nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
