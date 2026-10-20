#!/usr/bin/env python3
"""
Runtime Interceptor (PreToolUse Hook / Policy Enforcement Layer)
Intercepts tool executions BEFORE they reach the underlying OS or filesystem.
Enforces:
1. Workspace path confinement (blocks /tmp/, $HOME, or path traversal escapes).
2. Command boundary enforcement (blocks dangerous shell escapes, uncontained double-forks).
"""

import sys
import os
import json

class RuntimeInterceptor:
    def __init__(self, workspace_root: str):
        self.workspace_root = os.path.realpath(os.path.abspath(workspace_root))

    def intercept_file_write(self, target_path: str) -> bool:
        """
        Interception hook for write_to_file / replace_file_content.
        Blocks execution if the path escapes the workspace root.
        """
        expanded = os.path.expanduser(target_path)
        real_target = os.path.realpath(os.path.abspath(expanded))

        try:
            rel = os.path.relpath(real_target, self.workspace_root)
            if rel.startswith("..") or os.path.isabs(rel):
                sys.stderr.write(f"RUNTIME_POLICY_DENIAL: Write to '{target_path}' blocked. Path is outside workspace '{self.workspace_root}'.\n")
                return False
            return True
        except ValueError:
            sys.stderr.write(f"RUNTIME_POLICY_DENIAL: Illegal path '{target_path}'.\n")
            return False

    def intercept_command(self, command: str) -> bool:
        """
        Interception hook for run_command.
        Blocks uncontained fork bombs, raw rm -rf /, and escapes.
        """
        forbidden_patterns = [
            "rm -rf /",
            ":(){ :|:& };:",
            "> /dev/sda"
        ]
        for p in forbidden_patterns:
            if p in command:
                sys.stderr.write(f"RUNTIME_POLICY_DENIAL: Command blocked by safety policy (pattern '{p}').\n")
                return False
        return True

    def process_tool_call(self, tool_name: str, arguments: dict) -> bool:
        """
        Unified tool hook dispatcher.
        """
        if tool_name in ("write_to_file", "replace_file_content"):
            path = arguments.get("TargetFile") or arguments.get("path")
            if not path:
                return False
            return self.intercept_file_write(path)
        elif tool_name == "run_command":
            cmd = arguments.get("CommandLine") or arguments.get("command")
            if not cmd:
                return False
            return self.intercept_command(cmd)
        return True

if __name__ == "__main__":
    # Test runner
    interceptor = RuntimeInterceptor("/home/allcance/.gemini/antigravity/scratch")
    print("Testing /tmp write interception:")
    res = interceptor.process_tool_call("write_to_file", {"TargetFile": "/tmp/agent_unauthorized_escape.txt"})
    print("Allowed:", res)
