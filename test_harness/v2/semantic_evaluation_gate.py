#!/usr/bin/env python3
"""
Semantic Evaluation Gate
Detects subtle dissent manipulation where an agent sweeps genuine disagreements
under the rug by using phrases like 'there is no dissent' or 'unanimously agreed 100%'.
Requires structured trade-off boundaries to ratify decisions with divergent inputs.
"""

import re
from typing import Dict, Any, List

class SemanticEvaluationGate:
    @staticmethod
    def evaluate_dissent_handling(divergent_theses: List[str], final_report_text: str) -> Dict[str, Any]:
        """
        Adversarially tests whether genuine trade-offs were properly articulated
        or falsely flattened into a fake consensus.
        """
        has_divergent_theses = len(set(divergent_theses)) > 1
        text_lower = final_report_text.lower()

        # Check for false consensus red flags
        false_consensus_phrases = [
            "there is no dissent",
            "no dissent remaining",
            "agreed 100%",
            "unanimously agreed on option",
            "without any remaining trade-offs",
            "all debaters agreed without conflict"
        ]

        detected_false_consensus = [p for p in false_consensus_phrases if p in text_lower]

        # Check for legitimate trade-off matrix components
        has_tradeoff_section = any(k in text_lower for k in ["trade-off", "tradeoff", "dissenting position", "boundary"])
        has_boundary_trigger = any(k in text_lower for k in ["trigger", "when", "threshold", "if cluster", "if throughput"])

        if has_divergent_theses and detected_false_consensus:
            return {
                "passed": False,
                "verdict": "REJECTED",
                "reason": "MANUFACTURED_CONSENSUS_SNEAKY_WORDING",
                "detail": f"Debaters held divergent views {divergent_theses}, but final report claimed false consensus with: {detected_false_consensus}"
            }

        if has_divergent_theses and not (has_tradeoff_section and has_boundary_trigger):
            return {
                "passed": False,
                "verdict": "REJECTED",
                "reason": "MISSING_TRADEOFF_BOUNDARIES",
                "detail": "Divergent views were present, but report lacked explicit trade-off boundaries or revisit triggers."
            }

        return {
            "passed": True,
            "verdict": "APPROVED",
            "reason": None,
            "tradeoff_matrix_present": has_tradeoff_section,
            "boundary_trigger_present": has_boundary_trigger
        }
