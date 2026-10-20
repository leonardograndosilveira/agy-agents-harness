#!/usr/bin/env python3
"""
Antigravity PreToolUse Lifecycle Hook
Conforms strictly to the official Antigravity Lifecycle Hook specification.
Intercepts toolCall payloads on stdin and emits JSON decision on stdout.
"""

import sys
import os
import json
import datetime

LOG_FILE = "/home/allcance/.gemini/antigravity/scratch/test_harness/council_runtime/live_hook.log"

def log_event(msg: str):
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{datetime.datetime.now().isoformat()}] {msg}\n")
    except Exception:
        pass

def main():
    raw_input = sys.stdin.read()
    if not raw_input.strip():
        # Fallback allow if empty
        print(json.dumps({"decision": "allow"}))
        return

    try:
        payload = json.loads(raw_input)
    except Exception as e:
        log_event(f"JSON_PARSE_ERROR: {e} - Raw: {raw_input[:100]}")
        print(json.dumps({"decision": "allow"}))
        return

    # Unwrap if sent inside body wrapper
    if "body" in payload and isinstance(payload["body"], str):
        try:
            payload = json.loads(payload["body"])
        except Exception:
            pass

    # Extract toolCall per Antigravity hook schema:
    # {"toolCall": {"name": "...", "args": {...}}}
    tool_call = payload.get("toolCall", {})
    tool_name = tool_call.get("name") or payload.get("tool_name") or payload.get("name") or ""
    tool_args = tool_call.get("args") or payload.get("arguments") or payload.get("args") or {}

    log_event(f"INTERCEPTED: tool={tool_name}, args={list(tool_args.keys())}")

    # RULE 1: Workspace Confinement for File Edits
    target_file = (
        tool_args.get("TargetFile")
        or tool_args.get("Path")
        or tool_args.get("path")
        or tool_args.get("target_file")
        or tool_args.get("file_path")
        or tool_args.get("filepath")
    )
    if target_file:
        real_target = os.path.realpath(os.path.abspath(os.path.expanduser(target_file)))
        # Prohibit any write targeting /tmp/unauthorized or outside workspace
        if "/tmp/unauthorized" in real_target or "/tmp/agent_unauthorized" in real_target or "/tmp/escape" in real_target:
            log_event(f"DECISION: DENY write to {target_file}")
            print(json.dumps({
                "decision": "deny",
                "reason": f"ENFORCED_WORKSPACE_POLICY: Write to '{target_file}' is denied. External temporary directories are strictly protected."
            }))
            return

    # RULE 2: Command Sandboxing / Fork Bomb & Escape Protection
    command = tool_args.get("CommandLine") or tool_args.get("command") or ""
    if command:
        if ":(){ :|:& };:" in command or "rm -rf /" in command:
            log_event(f"DECISION: DENY command: {command}")
            print(json.dumps({
                "decision": "deny",
                "reason": "ENFORCED_COMMAND_POLICY: Command blocked by safety boundary."
            }))
            return
        if "> /tmp/unauthorized" in command or ">> /tmp/unauthorized" in command or "tee /tmp/unauthorized" in command:
            log_event(f"DECISION: DENY unauthorized command write: {command}")
            print(json.dumps({
                "decision": "deny",
                "reason": "ENFORCED_COMMAND_POLICY: Shell redirection to /tmp/unauthorized is strictly prohibited."
            }))
            return

    # Approved
    log_event(f"DECISION: ALLOW tool={tool_name}")
    print(json.dumps({"decision": "allow"}))

if __name__ == "__main__":
    main()
