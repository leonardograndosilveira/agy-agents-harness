#!/usr/bin/env python3
"""
Path Confinement Validator
Enforces that file write operations are strictly confined to the allowed workspace root,
blocking attempts to escape to /tmp, $HOME, or parent directories even when the OS user has write permissions.
"""

import os
from typing import Tuple

class PathConfinementValidator:
    def __init__(self, workspace_root: str):
        self.workspace_root = os.path.realpath(os.path.abspath(workspace_root))

    def is_path_confined(self, target_path: str) -> bool:
        """
        Resolves symlinks and relative path components.
        Returns True if and only if target_path resides within self.workspace_root.
        """
        # Expand user
        expanded = os.path.expanduser(target_path)
        real_target = os.path.realpath(os.path.abspath(expanded))

        # Check common prefix
        try:
            rel = os.path.relpath(real_target, self.workspace_root)
            # If rel begins with '..' or is absolute, it escapes the workspace
            return not (rel.startswith("..") or os.path.isabs(rel))
        except ValueError:
            return False

    def validate_write_attempt(self, target_path: str) -> Tuple[bool, str]:
        """
        Evaluates a write attempt against sandbox boundaries.
        """
        if not self.is_path_confined(target_path):
            return False, f"SANDBOX_CONFINEMENT_VIOLATION: Path '{target_path}' resolves outside workspace '{self.workspace_root}'."
        return True, "PATH_CONFINED"
