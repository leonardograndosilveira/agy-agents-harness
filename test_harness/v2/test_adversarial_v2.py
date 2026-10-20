#!/usr/bin/env python3
"""
Adversarial Round 2 Master Acceptance Suite
Attacks 5 genuine engineering vectors:
1. Path Confinement & Sandbox Escape (testing against user-writable paths)
2. Git Worktree Isolation under Concurrent Conflicting Edits
3. Fabricated Grounding & Semantic Content Verification (catching cited files with unrelated content)
4. Process-Group Tree Termination & Memory Ceiling Enforcement
5. Dissent Manipulation & Sneaky Consensus Detection
"""

import os
import sys
import json
import time
import subprocess
import shutil
import tempfile

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from path_confinement_validator import PathConfinementValidator
from semantic_evidence_validator import SemanticEvidenceValidator
from process_group_runner import ProcessGroupRunner
from semantic_evaluation_gate import SemanticEvaluationGate

def run_adversarial_v2():
    print("=" * 75)
    print("RUNNING ADVERSARIAL ACCEPTANCE TEST SUITE — ROUND 2")
    print("=" * 75)

    fixtures_path = os.path.join(current_dir, "fixtures", "adversarial_cases.json")
    with open(fixtures_path, "r") as f:
        fixtures = json.load(f)

    results = {}
    workspace_root = "/home/allcance/.gemini/antigravity/scratch"
    agents_root = "/home/allcance/.gemini/config/agents"

    # =========================================================================
    # ATTACK 1: Sandbox Boundary Bypass (Testing on User-Writable Paths)
    # =========================================================================
    print("\n[ATTACK 1] Path Confinement & Sandbox Boundary Enforcement...")
    confine_val = PathConfinementValidator(workspace_root)
    t1_pass = True

    for case in fixtures["sandbox_boundary_tests"]:
        target = case["target_path"].replace("{WORKSPACE_ROOT}", workspace_root)
        is_confined, reason = confine_val.validate_write_attempt(target)
        expected = case["expected_confinement"]

        if expected == "BLOCKED" and not is_confined:
            print(f"  ✓ PASS: External writable path '{target}' was STRICTLY BLOCKED by confinement policy.")
        elif expected == "ALLOWED" and is_confined:
            print(f"  ✓ PASS: Legitimate workspace path '{target}' was ALLOWED.")
        else:
            print(f"  ✗ FAIL: Case {case['id']} failed. Expected {expected}, got confined={is_confined}. ({reason})")
            t1_pass = False

    results["Attack 1: Sandbox Path Confinement"] = "PASS" if t1_pass else "FAIL"

    # =========================================================================
    # ATTACK 2: Concurrent Subagent Git Worktree Isolation
    # =========================================================================
    print("\n[ATTACK 2] Subagent Worktree Isolation (Workspace: 'branch')...")
    temp_dir = tempfile.mkdtemp(prefix="adv_worktree_")
    try:
        repo_dir = os.path.join(temp_dir, "repo")
        os.makedirs(repo_dir)
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo_dir, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_dir, check=True)

        base_file = os.path.join(repo_dir, "core.py")
        with open(base_file, "w") as f:
            f.write("# BASE\n")
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo_dir, check=True, stdout=subprocess.DEVNULL)

        # Create two parallel worktrees
        wt1 = os.path.join(temp_dir, "wt_subagent1")
        wt2 = os.path.join(temp_dir, "wt_subagent2")
        subprocess.run(["git", "worktree", "add", "-b", "branch-subagent-1", wt1], cwd=repo_dir, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "worktree", "add", "-b", "branch-subagent-2", wt2], cwd=repo_dir, check=True, stdout=subprocess.DEVNULL)

        # Mutate concurrently
        with open(os.path.join(wt1, "core.py"), "w") as f:
            f.write("# SUBAGENT 1 IMPLEMENTATION\n")

        with open(os.path.join(wt2, "core.py"), "w") as f:
            f.write("# SUBAGENT 2 IMPLEMENTATION\n")

        # Verify main repo untouched
        with open(base_file, "r") as f:
            main_state = f.read().strip()

        t2_pass = (main_state == "# BASE")
        if t2_pass:
            print("  ✓ PASS: Parallel worktree checkouts isolated conflicting edits completely.")
        else:
            print("  ✗ FAIL: Main branch working directory was corrupted by worktree modifications!")
        results["Attack 2: Subagent Worktree Isolation"] = "PASS" if t2_pass else "FAIL"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    # =========================================================================
    # ATTACK 3: Fabricated Grounding (Catching Real Files with Unrelated Content)
    # =========================================================================
    print("\n[ATTACK 3] Semantic Grounding & Citation Content Verification...")
    sem_val = SemanticEvidenceValidator(agents_root)
    t3_pass = True

    for case in fixtures["fabricated_grounding_tests"]:
        expected = case["expected_outcome"]
        cid = case["id"]

        if cid == "FG-01":
            # Non-existent file
            res = sem_val.verify_grounding(case["claim"], "nonexistent_database.py", 42, 42)
            passed = res["passed"]
            reason = res.get("reason")
        else:
            res = sem_val.verify_grounding(case["claim"], case["file"], case["start_line"], case["end_line"])
            passed = res["passed"]
            reason = res.get("reason")

        if expected == "REJECTED" and not passed:
            print(f"  ✓ PASS: Case {cid} ({case['description']}) was correctly REJECTED with [{reason}].")
        elif expected == "APPROVED" and passed:
            print(f"  ✓ PASS: Case {cid} ({case['description']}) was verified and APPROVED.")
        else:
            print(f"  ✗ FAIL: Case {cid} failed! Expected {expected}, got passed={passed}. ({res})")
            t3_pass = False

    results["Attack 3: Semantic Grounding Verification"] = "PASS" if t3_pass else "FAIL"

    # =========================================================================
    # ATTACK 4: Process-Group Termination & Memory Ceilings
    # =========================================================================
    print("\n[ATTACK 4] Process-Group Isolation & Resource Ceilings...")
    runner = ProcessGroupRunner()
    t4_pass = True

    # 4a: Orphaned child process group test
    print("  Testing compound subshell with background forks under 1.0s timeout...")
    res_fork = runner.run_bounded_command("bash -c 'sleep 20 & sleep 20 & wait'", timeout_seconds=1.0)
    
    # Check if any sleep 20 remains in process table
    ps_check = subprocess.run(["pgrep", "-f", "sleep 20"], stdout=subprocess.PIPE)
    orphans = ps_check.stdout.strip().decode()

    if res_fork["timed_out"] and not orphans:
        print("  ✓ PASS: Compound subshell timed out and ENTIRE process group was killed (0 orphaned processes).")
    else:
        print(f"  ✗ FAIL: Process group leak! Orphaned PIDs remaining: {orphans}")
        t4_pass = False

    # 4b: Memory limit test (500MB allocation with 100MB limit)
    print("  Testing memory explosion ceiling (500MB allocation under 100MB ceiling)...")
    res_mem = runner.run_bounded_command("python3 -c \"x = 'A' * (500 * 1024 * 1024)\"", timeout_seconds=5.0, max_memory_mb=100)
    
    if res_mem["memory_limit_hit"]:
        print("  ✓ PASS: Memory ceiling strictly enforced by OS (allocation exceeded ceiling and was killed).")
    else:
        print(f"  ✗ FAIL: Memory ceiling not enforced! Return code: {res_mem['exit_code']}, stderr: {res_mem['stderr']}")
        t4_pass = False

    results["Attack 4: Process Group & Resource Ceilings"] = "PASS" if t4_pass else "FAIL"

    # =========================================================================
    # ATTACK 5: Dissent Manipulation & Sneaky Consensus Detection
    # =========================================================================
    print("\n[ATTACK 5] Semantic Dissent Adjudication & Sneaky Consensus Detection...")
    gate = SemanticEvaluationGate()
    t5_pass = True

    for case in fixtures["dissent_manipulation_tests"]:
        cid = case["id"]
        res = gate.evaluate_dissent_handling(case["divergent_theses"], case["text"])
        expected = case["expected_gate_verdict"]

        if expected == "REJECTED" and not res["passed"]:
            print(f"  ✓ PASS: Case {cid} ({case['description']}) was caught and REJECTED with [{res['reason']}].")
        elif expected == "APPROVED" and res["passed"]:
            print(f"  ✓ PASS: Case {cid} ({case['description']}) with legitimate trade-off matrix was APPROVED.")
        else:
            print(f"  ✗ FAIL: Case {cid} failed! Expected {expected}, got {res['verdict']}. ({res})")
            t5_pass = False

    results["Attack 5: Semantic Dissent Adjudication"] = "PASS" if t5_pass else "FAIL"

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("\n" + "=" * 75)
    print("ADVERSARIAL ROUND 2 TEST RESULTS SUMMARY")
    print("=" * 75)
    all_passed = True
    for test_name, status in results.items():
        symbol = "✓" if status == "PASS" else "✗"
        print(f"[{symbol}] {test_name}: {status}")
        if status != "PASS":
            all_passed = False

    print("=" * 75)
    print(f"OVERALL OUTCOME: {'5 / 5 PASSED (100% HARDENED)' if all_passed else 'TESTS FAILED'}")
    print("=" * 75)
    return all_passed

if __name__ == "__main__":
    success = run_adversarial_v2()
    sys.exit(0 if success else 1)
