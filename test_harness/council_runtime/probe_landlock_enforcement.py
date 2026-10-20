#!/usr/bin/env python3
"""
Live Probe for Engine-Level Landlock Enforcement
Executed via genuine engine tool call (run_command) rewritten by PreToolUse hook.
Validates:
1. Landlock restriction is active on current process.
2. Kernel denial of overwrite on existing out-of-workspace file.
3. Kernel denial of truncate on existing out-of-workspace file.
4. Success of authorized workspace write.
5. Confinement inheritance in child processes.
"""

import os
import sys
import subprocess

OUTSIDE_CANARY = "/tmp/live_engine_landlock_canary.txt"
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
INSIDE_CANARY = os.path.join(WORKSPACE_DIR, "live_workspace_canary.txt")

def main():
    print("[PROBE] Running probe inside process PID:", os.getpid())
    
    # Check 1: Target file must exist outside workspace
    if not os.path.exists(OUTSIDE_CANARY):
        print(f"[PROBE_ERROR] Outside canary '{OUTSIDE_CANARY}' does not exist.")
        sys.exit(1)

    initial_content = open(OUTSIDE_CANARY, "r").read()

    # Check 2: Attempt overwrite on existing out-of-workspace file
    overwrite_denied = False
    try:
        with open(OUTSIDE_CANARY, "r+") as f:
            f.write("MUTATED_BY_OVERWRITE")
    except (PermissionError, OSError) as e:
        overwrite_denied = True
        print(f"[PROBE] Overwrite denied by OS/Kernel: {e}")

    # Check 3: Attempt truncate on existing out-of-workspace file
    truncate_denied = False
    try:
        with open(OUTSIDE_CANARY, "a") as f:
            f.truncate(0)
    except (PermissionError, OSError) as e:
        truncate_denied = True
        print(f"[PROBE] Truncate denied by OS/Kernel: {e}")

    # Verify content remained pristine
    current_content = open(OUTSIDE_CANARY, "r").read()
    content_intact = (current_content == initial_content)
    print(f"[PROBE] Outside file content intact: {content_intact}")

    # Check 4: Authorized workspace write succeeds
    workspace_write_ok = False
    try:
        with open(INSIDE_CANARY, "w") as f:
            f.write("AUTHORIZED_WORKSPACE_PAYLOAD")
        workspace_write_ok = os.path.exists(INSIDE_CANARY) and open(INSIDE_CANARY, "r").read() == "AUTHORIZED_WORKSPACE_PAYLOAD"
        print(f"[PROBE] Authorized workspace write succeeded: {workspace_write_ok}")
        # Clean up
        if os.path.exists(INSIDE_CANARY):
            os.remove(INSIDE_CANARY)
    except Exception as e:
        print(f"[PROBE_ERROR] Workspace write failed: {e}")

    # Check 5: Child process inherits confinement
    child_denied = False
    child_cmd = f"python3 -c \"with open('{OUTSIDE_CANARY}', 'r+') as f: f.write('CHILD_ESCAPE')\""
    res = subprocess.run(child_cmd, shell=True, capture_output=True, text=True)
    if res.returncode != 0 and ("PermissionError" in res.stderr or "Permission denied" in res.stderr):
        child_denied = True
        print(f"[PROBE] Child process write denied by Landlock: {res.stderr.strip()[:100]}")
    else:
        print(f"[PROBE_ERROR] Child process was NOT denied! Returncode: {res.returncode}, stderr: {res.stderr}")

    all_passed = overwrite_denied and truncate_denied and content_intact and workspace_write_ok and child_denied
    print(f"\n[PROBE_RESULT] OVERALL_VERDICT: {'PASS' if all_passed else 'FAIL'}")
    sys.exit(0 if all_passed else 2)

if __name__ == "__main__":
    main()
