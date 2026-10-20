#!/usr/bin/env python3
"""
Runtime Interceptor (PreToolUse Hook / Policy Enforcement Layer)
Intercepts tool executions BEFORE they reach the underlying OS or filesystem.
Enforces:
1. Workspace path confinement (blocks arbitrary writes outside workspace).
2. Command boundary enforcement (blocks out-of-workspace working directory and dangerous signatures).
"""

import sys
import os
import re
from typing import Dict, Any, List, Tuple

class RuntimeInterceptor:
    def __init__(self, workspace_root: str = None):
        if workspace_root:
            self.workspace_root = os.path.realpath(os.path.abspath(os.path.expanduser(workspace_root)))
        else:
            env_ws = os.environ.get("COUNCIL_WORKSPACE_ROOT")
            if env_ws:
                self.workspace_root = os.path.realpath(os.path.abspath(os.path.expanduser(env_ws)))
            else:
                self.workspace_root = os.path.realpath(os.getcwd())

    def intercept_file_write(self, target_path: str) -> bool:
        """
        Interception hook for write_to_file / replace_file_content.
        Blocks execution if the path escapes the workspace root.
        """
        if not target_path or not isinstance(target_path, str):
            sys.stderr.write("RUNTIME_POLICY_DENIAL: Missing or invalid target file path.\n")
            return False

        expanded = os.path.abspath(os.path.expanduser(target_path.strip()))
        real_target = os.path.realpath(expanded)

        parent_dir = os.path.dirname(expanded)
        real_parent = os.path.realpath(parent_dir) if os.path.exists(parent_dir) else parent_dir

        target_in_ws = real_target == self.workspace_root or real_target.startswith(self.workspace_root + os.sep)
        parent_in_ws = real_parent == self.workspace_root or real_parent.startswith(self.workspace_root + os.sep)

        if not (target_in_ws and parent_in_ws):
            sys.stderr.write(
                f"RUNTIME_POLICY_DENIAL: Write to '{target_path}' blocked. "
                f"Path '{real_target}' is outside workspace '{self.workspace_root}'.\n"
            )
            return False
        return True

    def intercept_command(self, command: str, cwd: str = None) -> bool:
        """
        Interception hook for run_command.
        Blocks out-of-workspace working directories and destructive signatures.
        """
        if cwd:
            real_cwd = os.path.realpath(os.path.abspath(os.path.expanduser(cwd)))
            if not (real_cwd == self.workspace_root or real_cwd.startswith(self.workspace_root + os.sep)):
                sys.stderr.write(f"RUNTIME_POLICY_DENIAL: Working dir '{cwd}' is outside workspace '{self.workspace_root}'.\n")
                return False

        forbidden_patterns = [
            "rm -rf /",
            "rm -rf /*",
            ":(){ :|:& };:",
            "> /dev/sda"
        ]
        for p in forbidden_patterns:
            if p in command:
                sys.stderr.write(f"RUNTIME_POLICY_DENIAL: Command blocked by safety policy (signature '{p}').\n")
                return False

        # Redirection check
        redirections = re.findall(r'(?:>|>>|tee\s+(?:-a\s+)?)(/([a-zA-Z0-9_\-./]+))', command)
        for _, path_body in redirections:
            full_path = "/" + path_body
            if not self.intercept_file_write(full_path):
                return False

        return True

    def process_tool_call(self, tool_name: str, arguments: dict) -> bool:
        """
        Unified tool hook dispatcher.
        """
        if tool_name in ("write_to_file", "write_file", "replace_file_content", "edit_file"):
            path = (
                arguments.get("TargetFile") 
                or arguments.get("Path") 
                or arguments.get("path") 
                or arguments.get("target_file")
            )
            if not path:
                return False
            return self.intercept_file_write(path)
        elif tool_name in ("run_command", "execute_command"):
            cmd = arguments.get("CommandLine") or arguments.get("command") or ""
            cwd = arguments.get("Cwd") or arguments.get("cwd")
            return self.intercept_command(cmd, cwd)
        return True

if __name__ == "__main__":
    interceptor = RuntimeInterceptor()
    print(f"Interceptor active for workspace: {interceptor.workspace_root}")
    res = interceptor.process_tool_call("write_to_file", {"TargetFile": "/tmp/unauthorized_test.txt"})
    print("Allowed (/tmp write):", res)
