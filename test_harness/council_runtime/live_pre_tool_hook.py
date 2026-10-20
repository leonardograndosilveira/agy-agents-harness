#!/usr/bin/env python3
"""
Antigravity PreToolUse Lifecycle Hook
Enforces Workspace Confinement, Fail-Closed Payload Validation, and Mutation Policy.

Architecture Boundary Notice:
- Hook-Level Enforcement: Operates at the engine tool dispatch layer before tools execute.
  Validates tool name, arguments, target file paths, working directories, and shell redirections
  against permitted workspace policies.
- OS-Level Confinement: Complements OS-level sandboxing (e.g. Antigravity's
  commandExecutionPolicy: sandbox, Linux namespaces, containers) for low-level syscall isolation.
"""

import sys
import os
import re
import json
import datetime
from typing import Dict, Any, List, Optional, Tuple

# Configuration via environment variables with portable fallbacks
DEFAULT_LOG_DIR = os.environ.get("COUNCIL_LOG_DIR", os.path.dirname(os.path.abspath(__file__)))
LOG_FILE = os.environ.get("COUNCIL_AUDIT_LOG", os.path.join(DEFAULT_LOG_DIR, "live_hook.log"))

# Mutating tools that require strict workspace confinement
MUTATING_FILE_TOOLS = {
    "write_file",
    "write_to_file",
    "edit_file",
    "replace_file_content",
    "append_file",
    "create_file"
}

MUTATING_EXEC_TOOLS = {
    "run_command",
    "execute_command",
    "bash"
}

PASS_THROUGH_MCP_SERVERS = {
    "ai-memory"
}

def log_event(msg: str, structured: Optional[Dict[str, Any]] = None):
    try:
        os.makedirs(os.path.dirname(os.path.abspath(LOG_FILE)), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            entry = {
                "timestamp": datetime.datetime.now().isoformat(),
                "message": msg,
                **(structured or {})
            }
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass

def get_allowed_workspaces(payload: Dict[str, Any]) -> List[str]:
    """
    Resolves permitted workspace roots in order of precedence:
    1. Explicit environment variable COUNCIL_WORKSPACE_ROOT
    2. Engine payload 'workspacePaths'
    3. Git repo root / Current working directory fallback
    """
    roots = []
    
    env_root = os.environ.get("COUNCIL_WORKSPACE_ROOT")
    if env_root:
        for r in env_root.split(os.pathsep):
            if r.strip():
                roots.append(os.path.realpath(os.path.abspath(os.path.expanduser(r.strip()))))
                
    payload_paths = payload.get("workspacePaths") or []
    if isinstance(payload_paths, list):
        for p in payload_paths:
            if isinstance(p, str) and p.strip():
                roots.append(os.path.realpath(os.path.abspath(os.path.expanduser(p.strip()))))

    # Fallback to repo root of this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
    roots.append(os.path.realpath(repo_root))

    # Also permit active development project trees in current user environment
    user_home = os.path.expanduser("~")
    for common_proj_root in [
        os.path.join(user_home, "projects"),
        os.path.join(user_home, ".gemini", "antigravity", "scratch")
    ]:
        if os.path.exists(common_proj_root):
            roots.append(os.path.realpath(common_proj_root))

    return list(set(roots))

def verify_path_confinement(target_path: str, allowed_workspaces: List[str]) -> Tuple[bool, str]:
    """
    Verifies that a target path (and its resolved symlink chain) strictly resides
    inside the permitted workspace boundary. Protects against:
    - Arbitrary out-of-workspace writes (/tmp, /etc, /var, ~, etc.)
    - Symlink redirection attacks
    - Directory traversal via '..'
    """
    if not target_path or not isinstance(target_path, str):
        return False, "INVALID_TARGET_PATH: Path is missing or not a string."

    expanded = os.path.abspath(os.path.expanduser(target_path.strip()))
    real_target = os.path.realpath(expanded)

    # Also resolve parent path to protect against symlinked or non-existent parent directories
    parent_dir = os.path.dirname(expanded)
    real_parent = os.path.realpath(parent_dir) if os.path.exists(parent_dir) else parent_dir

    for ws in allowed_workspaces:
        real_ws = os.path.realpath(ws)
        # Check that both target and its parent reside within allowed workspace
        target_in_ws = real_target == real_ws or real_target.startswith(real_ws + os.sep)
        parent_in_ws = real_parent == real_ws or real_parent.startswith(real_ws + os.sep)
        
        if target_in_ws and parent_in_ws:
            return True, "CONFINED"

    return False, (
        f"WORKSPACE_CONFINEMENT_VIOLATION: Write target '{target_path}' "
        f"(resolving to '{real_target}') is outside permitted workspaces: {allowed_workspaces}"
    )

def evaluate_command_safety(tool_args: Dict[str, Any], allowed_workspaces: List[str]) -> Tuple[bool, str]:
    """
    Audits execution command parameters for out-of-workspace working directories,
    destructive commands, and unauthorized file redirection attempts.
    """
    cmd = tool_args.get("CommandLine") or tool_args.get("command") or ""
    cwd = tool_args.get("Cwd") or tool_args.get("cwd") or ""

    # Verify working directory confinement if specified
    if cwd:
        cwd_ok, reason = verify_path_confinement(cwd, allowed_workspaces)
        if not cwd_ok:
            return False, f"UNAUTHORIZED_WORKING_DIR: Command working directory '{cwd}' is outside workspace."

    # Detect destructive system wipes or fork bombs
    if ":(){ :|:& };:" in cmd or "rm -rf /" in cmd or "rm -rf /*" in cmd:
        return False, "DESTRUCTIVE_COMMAND_BLOCKED: Command contains recognized destructive signature."

    # Audit shell output redirections (e.g. > /path, >> /path, tee /path)
    # Check if redirection targets an absolute path outside allowed workspaces
    PERMITTED_SPECIAL_TARGETS = {"/dev/null", "/dev/zero", "/dev/stdout", "/dev/stderr"}
    redirection_matches = re.findall(r'(?:>|>>|tee(?:\s+-a)?)\s*[\'"]?(/[^ \t\n\r\'";|&]+)[\'"]?', cmd)
    for redirect_target in redirection_matches:
        if redirect_target in PERMITTED_SPECIAL_TARGETS:
            continue
        is_ok, _ = verify_path_confinement(redirect_target, allowed_workspaces)
        if not is_ok:
            return False, (
                f"UNAUTHORIZED_REDIRECT_BLOCKED: Shell redirection target '{redirect_target}' "
                f"is outside permitted workspaces: {allowed_workspaces}"
            )

    return True, "SAFE"

def main():
    raw_input = sys.stdin.read()
    
    # 1. Fail-closed for empty input
    if not raw_input.strip():
        log_event("DENIED: Empty payload on stdin (Fail-closed)")
        print(json.dumps({
            "decision": "deny",
            "reason": "MALFORMED_HOOK_PAYLOAD: Received empty payload on hook stdin."
        }))
        return

    # 2. Fail-closed for invalid JSON
    try:
        payload = json.loads(raw_input)
    except Exception as e:
        log_event(f"DENIED: JSON parse error: {e}", {"raw": raw_input[:200]})
        print(json.dumps({
            "decision": "deny",
            "reason": f"MALFORMED_HOOK_PAYLOAD: JSON parse failure ({e})."
        }))
        return

    # Handle optional body wrapping
    if "body" in payload and isinstance(payload["body"], str):
        try:
            payload = json.loads(payload["body"])
        except Exception:
            pass

    # Extract tool call
    tool_call = payload.get("toolCall", {})
    tool_name = tool_call.get("name") or payload.get("tool_name") or payload.get("name") or ""
    tool_args = tool_call.get("args") or payload.get("arguments") or payload.get("args") or {}

    # Pass-through for ai-memory MCP tool calls to preserve established workflow
    if tool_name == "call_mcp_tool" and tool_args.get("ServerName") in PASS_THROUGH_MCP_SERVERS:
        log_event(f"ALLOWED_MCP_PASSTHROUGH: {tool_args.get('ServerName')}")
        print(json.dumps({"decision": "allow"}))
        return

    # Resolve allowed workspaces dynamically
    allowed_workspaces = get_allowed_workspaces(payload)

    # 3. Fail-closed for mutating file tools
    if tool_name in MUTATING_FILE_TOOLS:
        target_file = (
            tool_args.get("TargetFile")
            or tool_args.get("Path")
            or tool_args.get("path")
            or tool_args.get("target_file")
            or tool_args.get("file_path")
            or tool_args.get("filepath")
        )
        if not target_file:
            log_event(f"DENIED: Mutating tool '{tool_name}' missing target path", {"args": list(tool_args.keys())})
            print(json.dumps({
                "decision": "deny",
                "reason": f"MALFORMED_TOOL_CALL: Mutating tool '{tool_name}' missing target file parameter."
            }))
            return

        is_confined, reason = verify_path_confinement(target_file, allowed_workspaces)
        if not is_confined:
            log_event(f"DENIED: Write to '{target_file}' blocked", {"reason": reason})
            print(json.dumps({
                "decision": "deny",
                "reason": reason
            }))
            return

    # 4. Command Execution Audit
    if tool_name in MUTATING_EXEC_TOOLS:
        cmd_safe, cmd_reason = evaluate_command_safety(tool_args, allowed_workspaces)
        if not cmd_safe:
            log_event(f"DENIED: Command blocked: {cmd_reason}")
            print(json.dumps({
                "decision": "deny",
                "reason": cmd_reason
            }))
            return

    # Approved: Log decision and allow
    log_event(f"ALLOWED: tool={tool_name}", {"tool": tool_name})
    print(json.dumps({"decision": "allow"}))

if __name__ == "__main__":
    main()
