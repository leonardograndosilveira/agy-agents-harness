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

    def test_05_keyword_overlap_without_establishing_claim(self):
        """
        Defect: High keyword overlap without semantic support for the proposition.
        Must default to INSUFFICIENT.
        """
        source_text = "The PostgreSQL server configuration file specifies max_connections and shared_buffers settings."
        self._create_source("config.txt", source_text)
        
        invented_claim = "The PostgreSQL server configuration guarantees zero packet loss across read replicas."
        res = self.validator.verify_grounding(invented_claim, "config.txt", 1, 1)
        
        self.assertNotEqual(
            res["status"],
            "SUPPORTED",
            f"VULNERABILITY: Keyword overlap alone falsely established claim! Result: {res}"
        )
        self.assertEqual(res["status"], "INSUFFICIENT")

if __name__ == "__main__":
    unittest.main()
