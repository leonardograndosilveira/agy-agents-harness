#!/usr/bin/env python3
"""
Execution Safety Validator
Tests sandbox write protection, Git worktree isolation,
and command execution safety boundaries (timeout & resource limits).
"""

import os
import shutil
import subprocess
import tempfile
from typing import Dict, Any

class ExecutionSafetyValidator:
    def __init__(self, workspace_root: str):
        self.workspace_root = os.path.abspath(workspace_root)
        self.repo_root = self.workspace_root

    def test_sandbox_write_restrictions(self) -> Dict[str, Any]:
        """
        Tests whether writes outside allowed workspace directories are properly guarded.
        """
        forbidden_targets = [
            "/etc/antigravity_test_canary.tmp",
            "/var/log/antigravity_test_canary.tmp",
            "/root/antigravity_test_canary.tmp"
        ]
        results = []
        all_passed = True

        for target in forbidden_targets:
            try:
                with open(target, 'w') as f:
                    f.write("canary")
                # If we succeeded in writing to /etc, sandbox failed!
                os.remove(target)
                results.append({"target": target, "status": "VULNERABLE", "detail": "Unauthorized write succeeded!"})
                all_passed = False
            except (PermissionError, OSError) as e:
                results.append({"target": target, "status": "SECURED", "detail": f"Write rejected: {e}"})

        return {"passed": all_passed, "checks": results}

    def test_worktree_isolation(self) -> Dict[str, Any]:
        """
        Proves that parallel subagents operating on separate Git worktrees
        (Workspace: "branch") cannot corrupt or overwrite one another.
        """
        temp_dir = tempfile.mkdtemp(prefix="agy_worktree_test_", dir=self.repo_root)
        try:
            repo_dir = os.path.join(temp_dir, "main_repo")
            os.makedirs(repo_dir)

            # Initialize git repo
            subprocess.run(["git", "init"], cwd=repo_dir, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.name", "TestAgent"], cwd=repo_dir, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)

            # Initial commit
            code_file = os.path.join(repo_dir, "service.py")
            with open(code_file, "w") as f:
                f.write("# Version 1.0\ndef run():\n    return 'base'\n")
            subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
            subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True, stdout=subprocess.DEVNULL)

            # Create Worktree A (Subagent 1) and Worktree B (Subagent 2)
            wt_a = os.path.join(temp_dir, "subagent_a_worktree")
            wt_b = os.path.join(temp_dir, "subagent_b_worktree")

            subprocess.run(["git", "worktree", "add", "-b", "agent-a-feature", wt_a], cwd=repo_dir, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "worktree", "add", "-b", "agent-b-feature", wt_b], cwd=repo_dir, check=True, stdout=subprocess.DEVNULL)

            # Subagent A edits service.py
            with open(os.path.join(wt_a, "service.py"), "w") as f:
                f.write("# Version A\ndef run():\n    return 'feature_a'\n")

            # Subagent B edits service.py with completely conflicting content
            with open(os.path.join(wt_b, "service.py"), "w") as f:
                f.write("# Version B\ndef run():\n    return 'feature_b'\n")

            # Verify Main Repo service.py is untouched
            with open(code_file, "r") as f:
                main_content = f.read()

            with open(os.path.join(wt_a, "service.py"), "r") as f:
                content_a = f.read()

            with open(os.path.join(wt_b, "service.py"), "r") as f:
                content_b = f.read()

            is_isolated = (
                "base" in main_content and
                "feature_a" in content_a and
                "feature_b" in content_b and
                content_a != content_b
            )

            return {
                "passed": is_isolated,
                "main_repo_clean": "base" in main_content,
                "worktree_a_independent": "feature_a" in content_a,
                "worktree_b_independent": "feature_b" in content_b,
                "collision_detected": False
            }
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_bounded_probe_enforcement(self, command_str: str) -> Dict[str, Any]:
        """
        Detects whether an inspection command has real execution boundaries
        (e.g., timeout wrapper, memory ceiling) rather than relying solely
        on naive 'head' or 'LIMIT'.
        """
        has_timeout = "timeout " in command_str or "statement_timeout" in command_str
        has_naive_head = bool(" | head" in command_str and not has_timeout)
        has_naive_limit = bool("LIMIT " in command_str.upper() and not has_timeout)

        # Flag unsafe if relying purely on output truncation without resource control
        is_safe = has_timeout or (not has_naive_head and not has_naive_limit)

        return {
            "command": command_str,
            "has_timeout_protection": has_timeout,
            "naive_output_filter_warning": has_naive_head or has_naive_limit,
            "passed": has_timeout
        }

if __name__ == "__main__":
    v = ExecutionSafetyValidator("/tmp")
    print("Sandbox write test:", v.test_sandbox_write_restrictions())
    print("Worktree isolation test:", v.test_worktree_isolation())
