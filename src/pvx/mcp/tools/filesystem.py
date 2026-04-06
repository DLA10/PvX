import os
from pathlib import Path
from typing import Dict, Any, List

class FilesystemTool:
    """
    MCP tool for filesystem operations.
    Validates paths before execution.
    """
    def __init__(self, allowed_paths: List[str], blocked_paths: List[str]):
        self.allowed_paths = [Path(p).resolve() for p in allowed_paths]
        self.blocked_paths = [Path(p).resolve() for p in blocked_paths]

    def _validate_path(self, path_str: str) -> bool:
        try:
            resolved = Path(path_str).resolve()
        except Exception:
            return False
            
        in_allowed = any(resolved.is_relative_to(a) for a in self.allowed_paths)
        in_blocked = any(resolved.is_relative_to(b) for b in self.blocked_paths)
        
        return in_allowed and not in_blocked

    def read_file(self, path: str) -> Dict[str, Any]:
        if not self._validate_path(path):
            return {"error": f"Path '{path}' is not allowed"}
            
        try:
            with open(path, "r") as f:
                return {"content": f.read()}
        except Exception as e:
            return {"error": str(e)}

    def write_file(self, path: str, content: str) -> Dict[str, Any]:
        if not self._validate_path(path):
            return {"error": f"Path '{path}' is not allowed"}
            
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(content)
            return {"status": "success"}
        except Exception as e:
            return {"error": str(e)}

    def list_directory(self, path: str) -> Dict[str, Any]:
        if not self._validate_path(path):
            return {"error": f"Path '{path}' is not allowed"}
            
        try:
            return {"items": os.listdir(path)}
        except Exception as e:
            return {"error": str(e)}
