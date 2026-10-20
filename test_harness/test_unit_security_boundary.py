#!/usr/bin/env python3
"""
Unit Tests for P0: Security Boundary & Hook Enforcement
Tests workspace confinement, symlink traversal prevention, shell command safety,
fail-closed error handling, and ai-memory pass-through.
"""

import os
import sys
import json
import subprocess
import tempfile
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
HOOK_SCRIPT = os.path.join(PROJECT_ROOT, "test_harness", "council_runtime", "live_pre_tool_hook.py")

class TestSecurityBoundary(unittest.TestCase):
    def setUp(self):
        self.workspace_dir = tempfile.mkdtemp(prefix="council_test_ws_")
        self.env = os.environ.copy()
        self.env["COUNCIL_WORKSPACE_ROOT"] = self.workspace_dir
        self.env["COUNCIL_AUDIT_LOG"] = os.path.join(self.workspace_dir, "test_audit.log")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.workspace_dir, ignore_errors=True)

    def _call_hook(self, payload_str: str) -> dict:
        proc = subprocess.run(
            [sys.executable, HOOK_SCRIPT],
            input=payload_str,
            text=True,
            capture_output=True,
            env=self.env
        )
        self.assertEqual(proc.returncode, 0, f"Hook exited non-zero: {proc.stderr}")
        return json.loads(proc.stdout.strip())

    def test_out_of_workspace_write_rejected(self):
        """Unauthorized writes to arbitrary locations outside workspace must be denied."""
        targets = [
            "/tmp/arbitrary_file.txt",
            "/var/tmp/escape.txt",
            "/etc/critical_config",
            os.path.expanduser("~/.bashrc")
        ]
        for t in targets:
            payload = json.dumps({
                "toolCall": {
                    "name": "write_file",
                    "args": {"Path": t, "Content": "payload"}
                }
            })
            resp = self._call_hook(payload)
            self.assertEqual(resp.get("decision"), "deny", f"Failed to deny write to {t}")
            self.assertIn("WORKSPACE_CONFINEMENT_VIOLATION", resp.get("reason", ""))

    def test_in_workspace_write_allowed(self):
        """Authorized writes inside the designated workspace must be allowed."""
        safe_target = os.path.join(self.workspace_dir, "safe_canary.txt")
        payload = json.dumps({
            "toolCall": {
                "name": "write_file",
                "args": {"Path": safe_target, "Content": "hello"}
            }
        })
        resp = self._call_hook(payload)
        self.assertEqual(resp.get("decision"), "allow")

    def test_symlink_traversal_rejected(self):
        """Writing through directory traversal or symlinks outside workspace must be denied."""
        traversal_target = os.path.join(self.workspace_dir, "..", "escape_via_dotdot.txt")
        payload = json.dumps({
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": traversal_target, "CodeContent": "bad"}
            }
        })
        resp = self._call_hook(payload)
        self.assertEqual(resp.get("decision"), "deny")

    def test_fail_closed_empty_payload(self):
        """Empty input to hook must fail closed with deny."""
        resp = self._call_hook("")
        self.assertEqual(resp.get("decision"), "deny")
        self.assertIn("MALFORMED_HOOK_PAYLOAD", resp.get("reason", ""))

    def test_fail_closed_malformed_json(self):
        """Malformed JSON payload must fail closed with deny."""
        resp = self._call_hook("{broken_json: true")
        self.assertEqual(resp.get("decision"), "deny")
        self.assertIn("MALFORMED_HOOK_PAYLOAD", resp.get("reason", ""))

    def test_mutating_tool_missing_target(self):
        """Mutating file tool with no path argument must fail closed with deny."""
        payload = json.dumps({
            "toolCall": {
                "name": "write_file",
                "args": {"Content": "orphan_content"}
            }
        })
        resp = self._call_hook(payload)
        self.assertEqual(resp.get("decision"), "deny")
        self.assertIn("MALFORMED_TOOL_CALL", resp.get("reason", ""))

    def test_shell_redirection_out_of_workspace(self):
        """Shell command redirecting output to an arbitrary path outside workspace must be denied."""
        payload = json.dumps({
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "echo 'bad' > /tmp/shell_escape.txt"}
            }
        })
        resp = self._call_hook(payload)
        self.assertEqual(resp.get("decision"), "deny")
        self.assertIn("UNAUTHORIZED_REDIRECT_BLOCKED", resp.get("reason", ""))

    def test_shell_out_of_workspace_cwd(self):
        """Command attempting to run in an out-of-workspace working directory must be denied."""
        payload = json.dumps({
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "ls", "Cwd": "/tmp"}
            }
        })
        resp = self._call_hook(payload)
        self.assertEqual(resp.get("decision"), "deny")
        self.assertIn("UNAUTHORIZED_WORKING_DIR", resp.get("reason", ""))

    def test_ai_memory_passthrough(self):
        """ai-memory MCP tool calls must be passed through without interference."""
        payload = json.dumps({
            "toolCall": {
                "name": "call_mcp_tool",
                "args": {"ServerName": "ai-memory", "ToolName": "memory_status", "Arguments": {}}
            }
        })
        resp = self._call_hook(payload)
        self.assertEqual(resp.get("decision"), "allow")

if __name__ == "__main__":
    unittest.main()
