#!/usr/bin/env python3
"""
Independent Evaluation Gate
Acts as the external, non-self-grading audit layer for council outputs.
Evaluates evidence validity, slop/pseudo-math absence, consequence tagging,
and dissent preservation.
"""

import re
from typing import Dict, Any, List
from evidence_validator import EvidenceValidator

class EvaluationGate:
    def __init__(self, repo_root: str):
        self.evidence_validator = EvidenceValidator(repo_root)

    def audit_anti_slop(self, text: str) -> Dict[str, Any]:
        """
        Detects fabricated equations, pseudo-mathematical scoring formulas,
        and fake percentage confidences.
        """
        violations = []

        # Check for fabricated complexity formulas
        if re.search(r'\b[A-Z]{3,5}\(S,\s*\\?Theta\)', text) or re.search(r'\|\s*[VE]\s*\|\s*\+\s*\d', text):
            violations.append("FABRICATED_FORMULA: Detected invented scoring equation with arbitrary coefficients.")

        # Check for probabilistic sycophancy (e.g. "95% confident", "80% cognitive energy")
        syco_matches = re.findall(r'(\d{2}%\s+confident|\d{2}%\s+of\s+cognitive\s+energy)', text, re.IGNORECASE)
        if syco_matches:
            violations.append(f"PROBABILISTIC_SYCOPHANCY: Unsubstantiated quantitative claim: {syco_matches}")

        return {
            "passed": len(violations) == 0,
            "violations": violations
        }

    def audit_atomicity_and_rollback(self, text: str) -> Dict[str, Any]:
        """
        Verifies that shell commands are not falsely labeled as 'atomic'
        and that irreversible actions are not promised 60-second rollbacks.
        """
        violations = []

        # Check for false atomicity claims around bash
        if re.search(r'(atomic\s+pre-flight|bash.*set\s+-e.*atomic)', text, re.IGNORECASE):
            violations.append("FALSE_ATOMICITY: Chained bash command claimed to be atomic.")

        # Check for uncontained irreversible actions
        has_irreversible = "[IRREVERSIBLE" in text or "ONE-WAY DOOR" in text
        if "drop table" in text.lower() and not has_irreversible:
            violations.append("MISSING_IRREVERSIBLE_TAG: Destructive operation missing [IRREVERSIBLE] tag.")

        return {
            "passed": len(violations) == 0,
            "violations": violations
        }

    def audit_dissent_preservation(self, debaters_theses: List[str], final_report: str) -> Dict[str, Any]:
        """
        Verifies that when debaters legitimately disagree on engineering trade-offs,
        the final report does not manufacture a fake unanimous vote.
        """
        # Simple heuristic check: if debaters have opposing positions
        has_divergent_theses = len(set(debaters_theses)) > 1
        claims_unanimous = bool(re.search(r'unanimous.*(ratification|3\s*-\s*0|consensus)', final_report, re.IGNORECASE))
        has_dissent_matrix = bool(re.search(r'(dissent|trade-off.*matrix|unresolved)', final_report, re.IGNORECASE))

        # If there were genuine trade-offs, claiming unanimous without a dissent matrix fails
        if has_divergent_theses and claims_unanimous and not has_dissent_matrix:
            return {
                "passed": False,
                "error": "MANUFACTURED_CONSENSUS: Debaters had divergent theses, but report claimed unanimous agreement without documenting dissent."
            }

        return {
            "passed": True,
            "dissent_preserved": has_dissent_matrix,
            "legitimate_resolution": True
        }

    def run_full_evaluation(self, 
                            report_text: str, 
                            evidence_receipt: str, 
                            debater_theses: List[str] = None) -> Dict[str, Any]:
        """
        Executes all audit gates. Returns composite score and pass/fail status.
        """
        debater_theses = debater_theses or []
        evidence_res = self.evidence_validator.validate_receipt(evidence_receipt)
        slop_res = self.audit_anti_slop(report_text)
        safety_res = self.audit_atomicity_and_rollback(report_text)
        dissent_res = self.audit_dissent_preservation(debater_theses, report_text)

        all_passed = (
            evidence_res["passed"] and 
            slop_res["passed"] and 
            safety_res["passed"] and 
            dissent_res["passed"]
        )

        return {
            "overall_status": "APPROVED" if all_passed else "REJECTED",
            "all_passed": all_passed,
            "evidence_gate": evidence_res,
            "anti_slop_gate": slop_res,
            "safety_gate": safety_res,
            "dissent_preservation_gate": dissent_res
        }
