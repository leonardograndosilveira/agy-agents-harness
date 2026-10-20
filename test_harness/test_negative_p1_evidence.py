#!/usr/bin/env python3
"""
Negative Test Suite for P1 (Defensible Evidence Validation)
Demonstrates the original defects where keyword overlap and shallow numeric matching
falsely granted SUPPORTED status to invalid or contradicted conclusions.
"""

import os
import sys
import tempfile
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from semantic_evidence_validator import SemanticEvidenceValidator

class TestNegativeP1Evidence(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="council_p1_test_")
        self.validator = SemanticEvidenceValidator(self.tmp_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _create_source(self, filename: str, content: str) -> str:
        filepath = os.path.join(self.tmp_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return filepath

    def test_01_opposite_conclusion_with_identical_words_and_numbers(self):
        """
        Defect: Source reports failure, claim asserts success using identical words and numbers.
        Must NOT be granted SUPPORTED. Must be CONTRADICTED or INSUFFICIENT.
        """
        source_text = "Benchmark run: PostgreSQL connection pooling under 10k QPS had 120ms latency and failed SLA requirements."
        self._create_source("bench.txt", source_text)
        
        false_claim = "PostgreSQL connection pooling under 10k QPS had 120ms latency and passed SLA requirements."
        res = self.validator.verify_grounding(false_claim, "bench.txt", 1, 1)
        
        self.assertNotEqual(
            res["status"],
            "SUPPORTED",
            f"VULNERABILITY: False claim with reversed outcome was granted SUPPORTED! Result: {res}"
        )
        self.assertIn(res["status"], ["CONTRADICTED", "INSUFFICIENT"])

    def test_02_dropped_condition_is_not_supported(self):
        """
        Defect: Source has a strict condition ('only when X'), claim asserts unconditional or negated condition ('without X').
        Must NOT be granted SUPPORTED.
        """
        source_text = "Zero downtime schema migrations succeed only when lock_timeout is configured to 2s."
        self._create_source("condition.txt", source_text)
        
        unconditional_claim = "Zero downtime schema migrations succeed without lock_timeout."
        res = self.validator.verify_grounding(unconditional_claim, "condition.txt", 1, 1)
        
        self.assertNotEqual(
            res["status"],
            "SUPPORTED",
            f"VULNERABILITY: Dropped condition was granted SUPPORTED! Result: {res}"
        )
        self.assertIn(res["status"], ["CONTRADICTED", "INSUFFICIENT"])

    def test_03_reversed_comparison_is_not_supported(self):
        """
        Defect: Source states Option A < Option B (lower), claim states Option A > Option B (higher).
        Must NOT be granted SUPPORTED.
        """
        source_text = "Option A throughput was 500 QPS which is lower than Option B throughput of 2000 QPS."
        self._create_source("comparison.txt", source_text)
        
        reversed_claim = "Option A throughput was 500 QPS which is higher than Option B."
        res = self.validator.verify_grounding(reversed_claim, "comparison.txt", 1, 1)
        
        self.assertNotEqual(
            res["status"],
            "SUPPORTED",
            f"VULNERABILITY: Reversed comparative direction was granted SUPPORTED! Result: {res}"
        )
        self.assertIn(res["status"], ["CONTRADICTED", "INSUFFICIENT"])

    def test_04_mismatched_metric_units_and_context(self):
        """
        Defect: Source has 64 GB memory, claim asserts 64 GB/s throughput.
        Must NOT be granted SUPPORTED.
        """
        source_text = "The database server instance has 16 CPU cores and 64 GB memory."
        self._create_source("specs.txt", source_text)
        
        throughput_claim = "The database server instance achieved 64 GB/s network throughput."
        res = self.validator.verify_grounding(throughput_claim, "specs.txt", 1, 1)
        
        self.assertNotEqual(
            res["status"],
            "SUPPORTED",
            f"VULNERABILITY: Mismatched metric unit (GB vs GB/s) was granted SUPPORTED! Result: {res}"
        )
        self.assertEqual(res["status"], "INSUFFICIENT")

    def test_06_reversed_subject_object_relationships(self):
        """
        Defect: Subject-object relationship reversal (A replaces B vs B replaces A).
        Must NOT be granted SUPPORTED. Must be CONTRADICTED.
        """
        source_text = "Synchronous L1 cache replaces asynchronous Redis L2 cache in local single-process worker runtimes."
        self._create_source("reversal.txt", source_text)

        reversed_claim = "Asynchronous Redis L2 cache replaces synchronous L1 cache in local single-process worker runtimes."
        res = self.validator.verify_grounding(reversed_claim, "reversal.txt", 1, 1)

        self.assertNotEqual(res["status"], "SUPPORTED")
        self.assertEqual(res["status"], "CONTRADICTED")

    def test_07_correlation_presented_as_causation(self):
        """
        Defect: Correlation presented as causation.
        Must NOT be granted SUPPORTED. Must be INSUFFICIENT.
        """
        source_text = "Increased cache miss rates were observed alongside database connection pool exhaustion under load."
        self._create_source("causation.txt", source_text)

        causal_claim = "Increased cache miss rates directly caused database connection pool exhaustion under load."
        res = self.validator.verify_grounding(causal_claim, "causation.txt", 1, 1)

        self.assertNotEqual(res["status"], "SUPPORTED")
        self.assertEqual(res["status"], "INSUFFICIENT")

    def test_08_condition_removal_and_unsupported_generalization(self):
        """
        Defect: Condition removal and unsupported generalization.
        Must NOT be granted SUPPORTED.
        """
        source_text = "PreToolUse hook interception provides zero-overhead execution only when caching is enabled."
        self._create_source("generalization.txt", source_text)

        universal_claim = "PreToolUse hook interception provides zero-overhead execution in all environments."
        res = self.validator.verify_grounding(universal_claim, "generalization.txt", 1, 1)

        self.assertNotEqual(res["status"], "SUPPORTED")
        self.assertIn(res["status"], ["CONTRADICTED", "INSUFFICIENT"])

    def test_09_mismatched_experimental_scope_or_environment(self):
        """
        Defect: Mismatched experimental scope or environment.
        Must NOT be granted SUPPORTED. Must be INSUFFICIENT.
        """
        source_text = "In single-node synthetic fixture tests, Landlock sandbox added 0.2ms overhead."
        self._create_source("scope.txt", source_text)

        prod_claim = "In production multi-tenant clusters, Landlock sandbox added 0.2ms overhead."
        res = self.validator.verify_grounding(prod_claim, "scope.txt", 1, 1)

        self.assertNotEqual(res["status"], "SUPPORTED")
        self.assertEqual(res["status"], "INSUFFICIENT")

    def test_10_fabricated_benchmark_implications(self):
        """
        Defect: Fabricated benchmark implications.
        Must NOT be granted SUPPORTED. Must be INSUFFICIENT.
        """
        source_text = "Harness unit test fixture verified file overwrite denial on local scratch directory."
        self._create_source("implications.txt", source_text)

        fabricated_claim = "Harness unit test fixture proved distributed cluster security across cloud regions."
        res = self.validator.verify_grounding(fabricated_claim, "implications.txt", 1, 1)

        self.assertNotEqual(res["status"], "SUPPORTED")
        self.assertEqual(res["status"], "INSUFFICIENT")

    def test_11_source_contains_relevant_words_no_actual_support(self):
        """
        Defect: Source text containing relevant words but no actual support for the proposition.
        Must NOT be granted SUPPORTED. Must be INSUFFICIENT.
        """
        source_text = "Redis memory fragmentation and synchronous L1 cache evictions were discussed in the architecture review."
        self._create_source("words.txt", source_text)

        ungrounded_claim = "Synchronous L1 cache evictions provide sub-millisecond tail latency."
        res = self.validator.verify_grounding(ungrounded_claim, "words.txt", 1, 1)

        self.assertNotEqual(res["status"], "SUPPORTED")
        self.assertEqual(res["status"], "INSUFFICIENT")

    def test_12_valid_positive_controls_must_pass(self):
        """
        Positive control: Legitimate, fully grounded claims must pass with SUPPORTED status.
        """
        source_a = "PreToolUse hook intercepts tool calls at the engine boundary before execution."
        self._create_source("pos_a.txt", source_a)
        res_a = self.validator.verify_grounding(source_a, "pos_a.txt", 1, 1)
        self.assertEqual(res_a["status"], "SUPPORTED")

        source_b = "Council orchestrator implements fail-closed evaluation gate before releasing resolutions."
        self._create_source("pos_b.txt", source_b)
        claim_b = "Council orchestrator implements fail-closed evaluation gate before releasing resolutions."
        res_b = self.validator.verify_grounding(claim_b, "pos_b.txt", 1, 1)
        self.assertEqual(res_b["status"], "SUPPORTED")

if __name__ == "__main__":
    unittest.main()
