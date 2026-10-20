#!/usr/bin/env python3
"""
Unit Tests for P1: Evidence Verification & Provenance
Verifies four-state evidence classification (SUPPORTED, CONTRADICTED, INSUFFICIENT, UNVERIFIED),
quantitative alignment, rejection of missing receipts, and immutable provenance hashes.
"""

import os
import sys
import tempfile
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, os.path.join(SCRIPT_DIR, "v2"))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "council_runtime"))

from semantic_evidence_validator import SemanticEvidenceValidator
from council_orchestrator import EnforcedCouncilOrchestrator

class TestEvidenceVerification(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="evidence_test_")
        self.fixture_file = os.path.join(self.temp_dir, "architecture_spec.py")
        with open(self.fixture_file, "w", encoding="utf-8") as f:
            f.write(
                "# Line 1: Runtime architecture specification\n"
                "# Line 2: The pre-tool hook executes synchronously over standard I/O in 50 microseconds.\n"
                "# Line 3: Tool authorization checks must NOT rely on an asynchronous distributed Redis cache due to TOCTOU race conditions.\n"
                "# Line 4: In-memory L1 cache provides O(1) lookups and hermetic process isolation.\n"
                "# Line 5: Maximum execution timeout is bounded to 30s.\n"
            )
        self.validator = SemanticEvidenceValidator(self.temp_dir)
        self.orchestrator = EnforcedCouncilOrchestrator(
            workspace_root=self.temp_dir,
            agents_root=self.temp_dir
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_claim_supported(self):
        """A claim directly supported by the source slice must be classified as SUPPORTED."""
        claim = "The pre-tool hook executes synchronously over standard I/O in 50 microseconds."
        res = self.validator.verify_grounding(claim, self.fixture_file, 2, 2)
        self.assertEqual(res["status"], "SUPPORTED")
        self.assertTrue(res["passed"])
        self.assertIn("provenance_hash", res)
        self.assertEqual(len(res["provenance_hash"]), 16)

    def test_claim_contradicted_by_polarity(self):
        """
        Acceptance requirement: A claim quoting real lines but reversing the proposition
        must fail as CONTRADICTED even when keywords match.
        """
        # Line 3 says: "...must NOT rely on an asynchronous distributed Redis cache due to TOCTOU race conditions."
        # Claim asserts positive reliance on Redis:
        claim = "Tool authorization checks rely on an asynchronous distributed Redis cache for safe operation."
        res = self.validator.verify_grounding(claim, self.fixture_file, 3, 3)
        self.assertEqual(res["status"], "CONTRADICTED")
        self.assertFalse(res["passed"])
        self.assertEqual(res["reason"], "PROPOSITION_CONTRADICTED")

    def test_claim_insufficient_quantitative_mismatch(self):
        """
        Acceptance requirement: A claim asserting a numerical value not substantiated
        by the source slice must fail as INSUFFICIENT.
        """
        # Line 5 mentions 30s timeout, but claim asserts 10000 QPS throughput
        claim = "The architecture achieves 10000 QPS throughput and 99.9% uptime."
        res = self.validator.verify_grounding(claim, self.fixture_file, 5, 5)
        self.assertEqual(res["status"], "INSUFFICIENT")
        self.assertFalse(res["passed"])
        self.assertEqual(res["reason"], "QUANTITATIVE_MISMATCH")

    def test_claim_unverified_out_of_bounds(self):
        """Citing line numbers exceeding file length must return UNVERIFIED."""
        claim = "Some claim about non-existent line."
        res = self.validator.verify_grounding(claim, self.fixture_file, 99, 105)
        self.assertEqual(res["status"], "UNVERIFIED")
        self.assertFalse(res["passed"])

    def test_missing_evidence_receipt_rejected_by_orchestrator(self):
        """
        Acceptance requirement: Debater submitting proposal without mandatory evidence receipt
        must be halted with RATIFICATION_BLOCKED.
        """
        problem = "Determine agent state caching architecture"
        debaters = [
            {
                "name": "Debater_Builder",
                "thesis": "Use synchronous in-memory L1 cache.",
                "claim": "In-memory cache provides O(1) lookups and hermetic process isolation.",
                "file": self.fixture_file,
                "start_line": 4,
                "end_line": 4
            },
            {
                "name": "Debater_Speculator",
                "thesis": "Deploy distributed Redis cache immediately.",
                # Missing 'file' citation entirely!
                "claim": "Redis cache is superior for multi-agent synchronization."
            }
        ]
        draft_report = (
            "## Resolution\n"
            "Deploy Redis cache across all workers.\n"
            "- Revisit Trigger / Threshold: when workers exceed memory limits.\n"
            "- Trade-off matrix: L1 vs L2.\n"
        )
        res = self.orchestrator.process_council_turn(problem, debaters, draft_report, require_evidence=True)
        self.assertEqual(res["status"], "RATIFICATION_BLOCKED")
        self.assertIn("Unverified/Missing-Citations", res["final_action"])

if __name__ == "__main__":
    unittest.main()
