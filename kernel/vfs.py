"""
AI-DOS Kernel: Virtual Filesystem
Maps virtual paths to Python functions — /memory/, /tasks/, /system/, etc.
"""

import os
from typing import Callable, Dict, List, Optional, Tuple


class VFSError(Exception):
    pass


class VFSNode:
    """A virtual filesystem node — file or directory."""

    def __init__(self, name: str, is_dir: bool = False, reader: Callable = None, children: dict = None):
        self.name = name
        self.is_dir = is_dir
        self.reader = reader  # callable() -> str
        self.children = children or {}


class VirtualFileSystem:
    """
    Virtual filesystem with virtual paths backed by Python callables.

    Paths: /memory/, /tasks/, /system/, /profile/, /plugins/

    Usage:
        vfs = VirtualFileSystem()
        vfs.mount("/memory", reader=lambda: "stored facts here")
        print(vfs.read("/memory"))
        print(vfs.listdir("/"))
    """

    def __init__(self):
        self._root = VFSNode("", is_dir=True, children={})
        self._mounts: Dict[str, VFSNode] = {}

    def mount(self, path: str, reader: Callable = None, is_dir: bool = False):
        """
        Mount a handler at a virtual path.
        /memory -> reader returns content
        /tasks/ -> is_dir=True, children can be added
        """
        path = self._normalize(path)
        parts = [p for p in path.split("/") if p]

        if not parts:
            raise VFSError("Cannot mount at root")

        # Build hierarchy
        current = self._root
        for i, part in enumerate(parts):
            is_last = (i == len(parts) - 1)
            if part not in current.children:
                node_path = "/" + "/".join(parts[:i + 1])
                node = VFSNode(
                    name=part,
                    is_dir=is_dir if is_last else True,
                    reader=reader if is_last else None,
                )
                current.children[part] = node
                self._mounts[node_path] = node
                current = node
            else:
                current = current.children[part]
                if is_last:
                    current.reader = reader
                    current.is_dir = is_dir

    def read(self, path: str) -> str:
        """Read content from a virtual file path."""
        path = self._normalize(path)
        node = self._resolve(path)
        if node is None:
            raise VFSError(f"Path not found: {path}")
        if node.is_dir:
            items = self._format_dir(node)
            return f"[dir] {path}/\n{items}"
        if node.reader:
            try:
                content = node.reader()
                return content if isinstance(content, str) else str(content)
            except Exception as e:
                return f"[error] {e}"
        return f"[file] {path}"

    def listdir(self, path: str) -> List[Tuple[str, bool]]:
        """List directory contents. Returns [(name, is_dir), ...]."""
        path = self._normalize(path)
        node = self._resolve(path)
        if node is None:
            raise VFSError(f"Path not found: {path}")
        if not node.is_dir:
            return [(node.name, False)]
        results = []
        for name, child in node.children.items():
            results.append((name, child.is_dir))
        results.sort()
        return results

    def exists(self, path: str) -> bool:
        """Check if a virtual path exists."""
        path = self._normalize(path)
        return self._resolve(path) is not None

    def _normalize(self, path: str) -> str:
        path = path.strip()
        if not path.startswith("/"):
            path = "/" + path
        return os.path.normpath(path)

    def _resolve(self, path: str) -> Optional[VFSNode]:
        path = self._normalize(path)
        if path == "/":
            return self._root
        parts = [p for p in path.split("/") if p]
        current = self._root
        for part in parts:
            if part not in current.children:
                return None
            current = current.children[part]
        return current

    def _format_dir(self, node: VFSNode) -> str:
        lines = []
        for name, child in node.children.items():
            marker = "/" if child.is_dir else ""
            lines.append(f"  {name}{marker}")
        return "\n".join(lines) if lines else "  (empty)"
