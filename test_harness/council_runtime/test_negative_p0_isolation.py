#!/usr/bin/env python3
"""
Negative Test Suite for P0 (Workspace Isolation)
Exposes the original vulnerabilities in live_pre_tool_hook.py:
1. Implicit trust of ~/projects (outside COUNCIL_WORKSPACE_ROOT)
2. Shell commands executing writes without shell redirection (> or tee)
3. Symlink traversal / TOCTOU write vulnerabilities
"""

import os
import sys
import json
import tempfile
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import live_pre_tool_hook

class TestNegativeP0Isolation(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="council_p0_test_")
        self.workspace = os.path.join(self.tmp_dir, "exclusive_workspace")
        os.makedirs(self.workspace, exist_ok=True)
        
        # Another project directory that should NOT be writable
        self.unauthorized_project = os.path.join(os.path.expanduser("~/projects"), "unauthorized_peer_project")
        
        # Save env
        self.old_env = os.environ.get("COUNCIL_WORKSPACE_ROOT")
        os.environ["COUNCIL_WORKSPACE_ROOT"] = self.workspace

    def tearDown(self):
        if self.old_env is not None:
            os.environ["COUNCIL_WORKSPACE_ROOT"] = self.old_env
        else:
            os.environ.pop("COUNCIL_WORKSPACE_ROOT", None)
            
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_exclusive_allowlist_rejects_peer_projects(self):
        """
        Defect 1: Implicit trust of ~/projects.
        When COUNCIL_WORKSPACE_ROOT is explicitly set to workspace A,
        writes to ~/projects/other_project must be DENIED.
        """
        allowed = live_pre_tool_hook.get_allowed_workspaces({})
        # The allowed list MUST NOT contain ~/projects if workspace is explicitly configured
        user_projects = os.path.expanduser("~/projects")
        
        # Check path confinement for write to ~/projects/peer_project/canary.txt
        peer_target = os.path.join(user_projects, "peer_project", "canary.txt")
        is_confined, reason = live_pre_tool_hook.verify_path_confinement(peer_target, allowed)
        
        self.assertFalse(
            is_confined,
            f"VULNERABILITY: Path '{peer_target}' in ~/projects was ALLOWED despite exclusive workspace '{self.workspace}'!"
        )

    def test_02_shell_commands_without_redirection_are_blocked(self):
        """
        Defect 2: Shell commands executing writes without > or tee (e.g. python -c, touch, cp).
        Regex-only checks cannot detect writes inside code strings or binary invocations.
        The execution boundary must either OS-sandbox the command or reject untrusted shell execution.
        """
        # A command that writes to /tmp without '>' or 'tee'
        cmd = "python3 -c \"with open('/tmp/stealth_escape.txt', 'w') as f: f.write('escape')\""
        allowed = [self.workspace]
        
        # Under hardened check:
        res = live_pre_tool_hook.evaluate_command_safety({"CommandLine": cmd}, allowed)
        safe = res[0]
        self.assertFalse(
            safe,
            "VULNERABILITY: Shell command executing arbitrary file write was evaluated as SAFE!"
        )

    def test_03_symlink_traversal_write_is_blocked(self):
        """
        Defect 3: Symlink traversal / TOCTOU.
        A symlink inside the workspace pointing to /tmp/canary must NOT be permitted as a write target.
        """
        target_outside = os.path.join(self.tmp_dir, "outside_target.txt")
        symlink_inside = os.path.join(self.workspace, "symlink_escape.txt")
        
        try:
            os.symlink(target_outside, symlink_inside)
        except OSError:
            self.skipTest("Symlinks not supported in filesystem")

        allowed = [self.workspace]
        is_confined, reason = live_pre_tool_hook.verify_path_confinement(symlink_inside, allowed)
        self.assertFalse(
            is_confined,
            f"VULNERABILITY: Writing through symlink '{symlink_inside}' pointing to '{target_outside}' was permitted!"
        )

if __name__ == "__main__":
    unittest.main()
