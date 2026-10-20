#!/usr/bin/env python3
"""
Master Test Harness: 5 Adversarial Acceptance Tests
Verifies the three enforceable contracts and the independent evaluation gate.
"""

import sys
import os
import json

# Ensure test harness directory is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from evidence_validator import EvidenceValidator
from execution_safety_validator import ExecutionSafetyValidator
from evaluation_gate import EvaluationGate

def run_test_suite():
    print("=" * 70)
    print("STARTING COUNCIL AGENT ACCEPTANCE TEST SUITE (5 ADVERSARIAL TESTS)")
    print("=" * 70)

    repo_root = os.environ.get(
        "COUNCIL_AGENTS_ROOT",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "agents"))
    )
    exec_validator = ExecutionSafetyValidator(repo_root)
    evid_validator = EvidenceValidator(repo_root)
    gate = EvaluationGate(repo_root)

    results = {}

    # -------------------------------------------------------------
    # TEST 1: Verify actual sandbox settings & deny unauthorized writes
    # -------------------------------------------------------------
    print("\n[TEST 1] Testing OS / Sandbox write boundary...")
    t1_res = exec_validator.test_sandbox_write_restrictions()
    if t1_res["passed"]:
        print("  ✓ PASS: Unauthorized system writes were strictly rejected by OS/permissions.")
    else:
        print("  ✗ FAIL: System write succeeded to protected directory!")
    results["Test 1 (Sandbox Write Boundary)"] = "PASS" if t1_res["passed"] else "FAIL"

    # -------------------------------------------------------------
    # TEST 2: Prove parallel worktrees cannot overwrite one another
    # -------------------------------------------------------------
    print("\n[TEST 2] Testing Git Worktree Isolation (Workspace: 'branch')...")
    t2_res = exec_validator.test_worktree_isolation()
    if t2_res["passed"]:
        print("  ✓ PASS: Parallel worktrees operated concurrently on conflicting edits with ZERO collision.")
    else:
        print("  ✗ FAIL: Worktree isolation collision detected!")
    results["Test 2 (Worktree Isolation)"] = "PASS" if t2_res["passed"] else "FAIL"

    # -------------------------------------------------------------
    # TEST 3: Reject fabricated FILE:LINE references & fake benchmarks
    # -------------------------------------------------------------
    print("\n[TEST 3] Testing Evidence Validator on Hallucinated vs. Valid Citations...")
    # 3a: Valid citation
    valid_receipt = "Verified implementation in [council-moderator.md:1-20] showing YAML frontmatter."
    val_check = evid_validator.validate_receipt(valid_receipt)

    # 3b: Hallucinated citation
    fake_receipt = "Empirically verified in [phantom_database_cluster.py:9999] under 10k QPS."
    fake_check = evid_validator.validate_receipt(fake_receipt)

    t3_passed = val_check["passed"] and (not fake_check["passed"])
    if t3_passed:
        print(f"  ✓ PASS: Legitimate citation accepted ({val_check['verified'][0]['citation']}).")
        print(f"  ✓ PASS: Hallucinated citation caught and rejected: '{fake_check['failed'][0]['error']}'")
    else:
        print("  ✗ FAIL: Fabricated citation slipped through or valid citation was rejected!")
    results["Test 3 (Reject Fabricated Evidence)"] = "PASS" if t3_passed else "FAIL"

    # -------------------------------------------------------------
    # TEST 4: Detect unsafe database / shell probes despite LIMIT / head
    # -------------------------------------------------------------
    print("\n[TEST 4] Testing Resource-Bounding on Command Probes (Timeout vs Naive Filter)...")
    naive_cmd = "cat massive_log.txt | head -n 50"
    safe_cmd = "timeout 5s cat massive_log.txt | head -n 50"

    t4_naive = exec_validator.test_bounded_probe_enforcement(naive_cmd)
    t4_safe = exec_validator.test_bounded_probe_enforcement(safe_cmd)

    t4_passed = (not t4_naive["passed"]) and t4_safe["passed"]
    if t4_passed:
        print(f"  ✓ PASS: Naive command '{naive_cmd}' correctly flagged (missing timeout).")
        print(f"  ✓ PASS: Guarded command '{safe_cmd}' approved.")
    else:
        print("  ✗ FAIL: Failed to differentiate naive output truncation from real resource bounding!")
    results["Test 4 (Resource-Bounded Probes)"] = "PASS" if t4_passed else "FAIL"

    # -------------------------------------------------------------
    # TEST 5: Preserve dissent when evidence cannot resolve a trade-off
    # -------------------------------------------------------------
    print("\n[TEST 5] Testing Independent Evaluation Gate: Dissent Preservation...")
    theses = [
        "Debater 1 recommends Synchronous Strong Consistency (high read latency)",
        "Debater 2 recommends Eventual Consistency with Async Queues (high throughput)"
    ]

    # Report A falsely manufactures 3-0 consensus
    flawed_report = """
    # Final Report
    The council unanimously ratified (3 - 0) that Synchronous Strong Consistency is optimal everywhere.
    """
    gate_flawed = gate.run_full_evaluation(flawed_report, valid_receipt, theses)

    # Report B properly preserves dissent matrix
    honest_report = """
    # Final Report: Adjudicated Decision with Documented Dissent
    Layer 0: Decision Anchor: Adopt Synchronous Strong Consistency for Ledger mutations; Eventual Consistency for Analytics.
    Layer 1: Trade-off & Dissent Matrix:
    - Debater 1 defended data integrity for finance.
    - Debater 2 noted write-scaling bottlenecks under high concurrency.
    Boundary Trigger: Route analytics queries to read-replicas.
    """
    gate_honest = gate.run_full_evaluation(honest_report, valid_receipt, theses)

    t5_passed = (gate_flawed["overall_status"] == "REJECTED") and (gate_honest["overall_status"] == "APPROVED")
    if t5_passed:
        print("  ✓ PASS: Manufactured consensus was REJECTED by the Evaluation Gate.")
        print("  ✓ PASS: Report with documented Dissent Matrix was APPROVED.")
    else:
        print(f"  ✗ FAIL: Evaluation gate dissent check failed. Flawed: {gate_flawed['overall_status']}, Honest: {gate_honest['overall_status']}")
    results["Test 5 (Dissent Preservation Gate)"] = "PASS" if t5_passed else "FAIL"

    # -------------------------------------------------------------
    # FINAL SUMMARY
    # -------------------------------------------------------------
    print("\n" + "=" * 70)
    print("TEST SUITE RESULTS SUMMARY")
    print("=" * 70)
    all_pass = True
    for test_name, status in results.items():
        symbol = "✓" if status == "PASS" else "✗"
        print(f"[{symbol}] {test_name}: {status}")
        if status != "PASS":
            all_pass = False

    print("=" * 70)
    if all_pass:
        print("OVERALL RESULT: 5 / 5 TESTS PASSED (100% SUCCESS)")
    else:
        print("OVERALL RESULT: SOME TESTS FAILED")
    print("=" * 70)

    return all_pass

if __name__ == "__main__":
    success = run_test_suite()
    sys.exit(0 if success else 1)
