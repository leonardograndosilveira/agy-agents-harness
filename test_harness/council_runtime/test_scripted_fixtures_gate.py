#!/usr/bin/env python3
"""
Scripted Fixtures Evaluation Gate Suite (Unit Test Layer)
Tests evaluation gate logic using deterministic simulated debater fixtures.
NOTE: This is a unit test suite testing validator logic; for real engine execution,
see test_live_council_e2e.py.
"""

import os
import sys
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRATCH_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
HARNESS_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, HARNESS_DIR)

from council_orchestrator import EnforcedCouncilOrchestrator

def test_adversarial_flawed_proposal(orchestrator: EnforcedCouncilOrchestrator):
    print("\n" + "="*70)
    print("TEST 1: Adversarial Flawed Proposal (Fail-Closed Ratification)")
    print("="*70)

    problem = "Agent runtime state caching strategy"
    
    # Flawed debater output: asserts ungrounded numbers, cites unrelated code
    debaters_outputs = [
        {
            "name": "Debater_1_Builder",
            "thesis": "Synchronous L1 in-memory cache is simple and fast.",
            "claim": "Live hook runs stdio synchronously",
            "file": os.path.join(SCRIPT_DIR, "live_pre_tool_hook.py"),
            "start_line": 8,
            "end_line": 11
        },
        {
            "name": "Debater_2_Advocate",
            "thesis": "Distributed Redis cache should be used immediately.",
            "claim": "Redis provides +300% throughput and guarantees 85% CPU cap.",
            # Fabricated citation targeting lines that do NOT discuss throughput or CPU
            "file": os.path.join(SCRIPT_DIR, "live_pre_tool_hook.py"),
            "start_line": 1,
            "end_line": 5
        }
    ]

    # Moderation draft that contains pseudo-math, ungrounded metrics, false atomicity, and fake consensus
    draft_report = (
        "## Council Resolution Report: Cache Strategy\n\n"
        "Unanimous ratification 3-0 achieved: All debaters agreed to deploy Redis.\n"
        "Performance projection: +300% throughput and maintaining 85% CPU saturation threshold.\n"
        "Deployment plan: Chained bash script provides atomic pre-flight setup.\n"
        "Formula: Score = 1.5 * |E| + 6C.\n"
    )

    result = orchestrator.process_council_turn(problem, debaters_outputs, draft_report)
    print(f"Outcome Status: {result['status']}")
    print(f"Action: {result['final_action']}")
    
    assert result["status"] == "RATIFICATION_BLOCKED", f"Expected RATIFICATION_BLOCKED, got {result['status']}"
    assert result["gate_passed"] is False, "Expected gate_passed to be False"
    
    # Verify specific gate failures
    assert not result["slop_audit"]["passed"], "Expected anti-slop audit failure"
    assert not result["safety_audit"]["passed"], "Expected safety/atomicity audit failure"
    assert not result["quantitative_audit"]["passed"], "Expected quantitative completeness failure"
    print("--> PASS: Adversarial proposal was blocked with zero false approvals.")

def test_legitimate_council_proposal(orchestrator: EnforcedCouncilOrchestrator):
    print("\n" + "="*70)
    print("TEST 2: Legitimate Council Proposal with Grounded Evidence")
    print("="*70)

    problem = "Agent runtime state caching strategy"

    # Authentic debaters outputs derived from live subagent responses
    debaters_outputs = [
        {
            "name": "Debater_1_Ergonomist",
            "thesis": "Implement synchronous in-memory L1 cache for agent state to maximize developer velocity and preserve microsecond tool lifecycle hooks.",
            "claim": "The hook relies on standard library imports sys os re json datetime",
            "file": os.path.join(SCRIPT_DIR, "live_pre_tool_hook.py"),
            "start_line": 14,
            "end_line": 20
        },
        {
            "name": "Debater_2_Empirical_SRE",
            "thesis": "Agent execution state and pre-tool authorization must reside in a synchronous process-local L1 cache to eliminate TOCTOU race conditions and cluster-wide blast radius.",
            "claim": "The verify_path_confinement function verifies that target_path strictly resides inside the permitted workspace boundary",
            "file": os.path.join(SCRIPT_DIR, "live_pre_tool_hook.py"),
            "start_line": 95,
            "end_line": 125
        }
    ]

    # Grounded draft report: preserves trade-offs, cites verified boundary conditions, no pseudo-math
    grounded_report = (
        "## Council Resolution: Agent Runtime Cache Architecture\n\n"
        "### Decision & Synthesis\n"
        "The Council ratifies a **Synchronous Process-Local L1 Cache** for hot-path agent state and tool lifecycle authorization.\n\n"
        "### Dissent & Trade-Off Matrix\n"
        "| Architecture | Strengths | Failure Mode / Operational Risk |\n"
        "| :--- | :--- | :--- |\n"
        "| Synchronous L1 (Local) | Zero network hops, microsecond execution, hermetic testing | Process heap bounded; requires sticky routing in multi-node |\n"
        "| Asynchronous Redis L2 | Cross-worker visibility | TOCTOU race conditions during async invalidation; network partition blast radius |\n\n"
        "### Operational Boundaries & Falsification\n"
        "- Consequence Level: [REVERSIBLE] for cache abstraction; [IRREVERSIBLE / ONE-WAY DOOR] for unconfined OS tool dispatches.\n"
        "- Revisit Trigger / Threshold: When agent runtime workers are horizontally scaled across a multi-node cluster without session affinity, or when process heap memory exceeds threshold limits.\n"
        "- Falsification Condition: This resolution fails and must transition to distributed coordination when stateless multi-pod routing is deployed.\n"
    )

    result = orchestrator.process_council_turn(problem, debaters_outputs, grounded_report)
    print(f"Outcome Status: {result['status']}")
    print(f"Action: {result['final_action']}")

    assert result["status"] == "RATIFIED", f"Expected RATIFIED, got {result['status']}: {result.get('final_action')}"
    assert result["gate_passed"] is True, "Expected gate_passed to be True"
    assert result["slop_audit"]["passed"], "Anti-slop check must pass"
    assert result["safety_audit"]["passed"], "Safety check must pass"
    assert result["dissent_audit"]["passed"], "Dissent check must pass"
    assert result["quantitative_audit"]["passed"], "Quantitative audit must pass"
    print("--> PASS: Legitimate proposal successfully ratified with verified evidence.")

def main():
    orchestrator = EnforcedCouncilOrchestrator(
        workspace_root=SCRATCH_ROOT,
        agents_root=SCRATCH_ROOT
    )
    
    test_adversarial_flawed_proposal(orchestrator)
    test_legitimate_council_proposal(orchestrator)
    
    print("\n" + "="*70)
    print("ALL LIVE COUNCIL VERIFICATION TESTS PASSED (2/2)")
    print("="*70)

if __name__ == "__main__":
    main()
