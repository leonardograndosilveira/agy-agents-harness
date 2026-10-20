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

    def test_04_landlock_blocks_overwrite_and_truncate_outside_workspace(self):
        """
        Defect 4: Landlock omitting WRITE_FILE and TRUNCATE allows mutating existing files outside workspace.
        Creates an existing file outside workspace, then runs sandboxed child attempting:
        1. Overwrite existing file content (open with 'r+' or 'w')
        2. Truncate existing file (truncate(0))
        Both must be denied by Landlock kernel enforcement.
        Also asserts multi_replace_file_content is in MUTATING_FILE_TOOLS.
        """
        self.assertIn("multi_replace_file_content", live_pre_tool_hook.MUTATING_FILE_TOOLS)

        from landlock_sandbox import run_sandboxed_command, is_landlock_supported
        if not is_landlock_supported():
            self.skipTest("Landlock not supported on this kernel")

        existing_outside = os.path.join(self.tmp_dir, "existing_outside.txt")
        with open(existing_outside, "w") as f:
            f.write("ORIGINAL_UNTOUCHED_CONTENT")

        # Child command attempts both overwrite and truncate on existing outside file
        probe_script = os.path.join(self.workspace, "probe.py")
        with open(probe_script, "w") as f:
            f.write(
                f"import sys\n"
                f"path = {repr(existing_outside)}\n"
                f"try:\n"
                f"    with open(path, 'r+') as f: f.write('OVERWRITTEN')\n"
                f"    sys.exit(101)\n"
                f"except (PermissionError, OSError):\n"
                f"    pass\n"
                f"try:\n"
                f"    with open(path, 'a') as f: f.truncate(0)\n"
                f"    sys.exit(102)\n"
                f"except (PermissionError, OSError):\n"
                f"    pass\n"
                f"sys.exit(0)\n"
            )

        res = run_sandboxed_command(
            f"python3 {probe_script}",
            allowed_workspaces=[self.workspace],
            cwd=self.workspace
        )

        self.assertEqual(
            res.returncode, 0,
            f"VULNERABILITY: Landlock failed to block overwrite or truncate! Code: {res.returncode}. Output: {res.stderr}"
        )

        # Confirm file on disk remains original
        with open(existing_outside, "r") as f:
            content = f.read()
        self.assertEqual(content, "ORIGINAL_UNTOUCHED_CONTENT")

    def test_05_multi_target_mutation_rejects_if_any_target_escapes(self):
        """
        Defect 5: Multi-target tools (e.g. multi_replace_file_content) with multiple file targets.
        If any single target in a batch edit resolves outside the workspace, the entire call
        must be fail-closed DENIED.
        """
        allowed = [self.workspace]
        valid_in_ws = os.path.join(self.workspace, "valid.txt")
        invalid_outside = os.path.join(self.tmp_dir, "outside.txt")

        # Case A: TargetFiles list with mixed targets
        tool_args_list = {"TargetFiles": [valid_in_ws, invalid_outside]}
        targets = live_pre_tool_hook.extract_mutation_targets(tool_args_list)
        self.assertEqual(len(targets), 2)
        # Any outside must fail verification
        has_escape = any(not live_pre_tool_hook.verify_path_confinement(t, allowed)[0] for t in targets)
        self.assertTrue(has_escape, "Failed to detect out-of-workspace target in TargetFiles list!")

        # Case B: edits list with dicts
        tool_args_edits = {
            "edits": [
                {"TargetFile": valid_in_ws, "ReplacementContent": "ok"},
                {"TargetFile": invalid_outside, "ReplacementContent": "evil"}
            ]
        }
        targets_edits = live_pre_tool_hook.extract_mutation_targets(tool_args_edits)
        self.assertIn(invalid_outside, targets_edits)

        # Case C: changes dict mapping paths to edits
        tool_args_changes = {
            "changes": {
                valid_in_ws: [{"old": "a", "new": "b"}],
                invalid_outside: [{"old": "c", "new": "d"}]
            }
        }
        targets_changes = live_pre_tool_hook.extract_mutation_targets(tool_args_changes)
        self.assertIn(invalid_outside, targets_changes)

        # Case D: All targets valid
        valid_b = os.path.join(self.workspace, "sub", "valid_b.txt")
        all_valid_args = {"TargetFiles": [valid_in_ws, valid_b]}
        targets_valid = live_pre_tool_hook.extract_mutation_targets(all_valid_args)
        all_ok = all(live_pre_tool_hook.verify_path_confinement(t, allowed)[0] for t in targets_valid)
        self.assertTrue(all_ok)

    def test_06_landlock_unavailable_fails_closed(self):
        """
        Defect 6: Fail-closed requirement when Landlock is unavailable or unsupported.
        """
        from unittest.mock import patch
        with patch("landlock_sandbox.is_landlock_supported", return_value=False):
            safe, reason, cmd = live_pre_tool_hook.evaluate_command_safety(
                {"CommandLine": "echo test"},
                [self.workspace]
            )
            self.assertFalse(safe, "Hook must FAIL CLOSED when Landlock is unsupported!")
            self.assertIn("OS_SANDBOX_UNAVAILABLE", reason)
            self.assertIsNone(cmd)

    def test_07_child_processes_inherit_landlock_confinement(self):
        """
        Defect 7: Confinement must be inherited across fork/exec (children and grandchild processes).
        """
        from landlock_sandbox import run_sandboxed_command, is_landlock_supported
        if not is_landlock_supported():
            self.skipTest("Landlock not supported on this kernel")

        existing_outside = os.path.join(self.tmp_dir, "outside_child_target.txt")
        with open(existing_outside, "w") as f:
            f.write("CHILD_ORIGINAL")

        # Spawn a shell that spawns a subshell that spawns python attempting mutation
        nested_cmd = (
            f"bash -c \"bash -c 'python3 -c \\\"with open({repr(existing_outside)}, \\'w\\') as f: f.write(\\'MUTATED\\')\\\"'\""
        )
        res = run_sandboxed_command(
            nested_cmd,
            allowed_workspaces=[self.workspace],
            cwd=self.workspace
        )
        # Should fail with PermissionError in Python (exit code != 0)
        self.assertNotEqual(res.returncode, 0)
        with open(existing_outside, "r") as f:
            content = f.read()
        self.assertEqual(content, "CHILD_ORIGINAL", "Child process escaped Landlock sandbox!")

if __name__ == "__main__":
    unittest.main()
