#!/usr/bin/env python3
"""
Enforced Council Orchestrator
Wired directly into the independent Evaluation Gate.
Demonstrates Fail-Closed Behavior: if evidence verification fails, false consensus is detected,
citations are contradicted/insufficient, or required evidence receipts are missing,
the orchestrator halts execution, sets status RATIFICATION_BLOCKED, and refuses to publish.
"""

import sys
import os
from typing import Dict, Any, List

# Path imports
test_harness_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
v2_dir = os.path.join(test_harness_dir, "v2")
sys.path.insert(0, test_harness_dir)
sys.path.insert(0, v2_dir)

from semantic_evidence_validator import SemanticEvidenceValidator
from semantic_evaluation_gate import SemanticEvaluationGate
from evaluation_gate import EvaluationGate

class EnforcedCouncilOrchestrator:
    def __init__(self, workspace_root: str = None, agents_root: str = None):
        self.workspace_root = workspace_root or os.environ.get("COUNCIL_WORKSPACE_ROOT") or os.getcwd()
        self.agents_root = agents_root or os.environ.get("COUNCIL_AGENTS_ROOT") or self.workspace_root
        self.evidence_validator = SemanticEvidenceValidator(self.agents_root)
        self.evaluation_gate = EvaluationGate(self.agents_root)
        self.dissent_gate = SemanticEvaluationGate()

    def process_council_turn(self, 
                             problem_statement: str, 
                             debaters_outputs: List[Dict[str, Any]], 
                             draft_resolution_report: str,
                             require_evidence: bool = True) -> Dict[str, Any]:
        """
        Runs the independent evaluation gate on the council's generated outputs.
        Enforces FAIL-CLOSED ratification.
        """
        audit_trail = {
            "problem": problem_statement,
            "evidence_audits": [],
            "gate_passed": True,
            "status": "PENDING"
        }

        # 1. Audit every debater's evidence receipt
        theses = []
        verified_evidence_texts = []

        if len(debaters_outputs) < 2:
            audit_trail["gate_passed"] = False
            audit_trail["evidence_audits"].append({
                "debater": "Council_Size",
                "claim": "NONE",
                "citation": "NONE",
                "result": {
                    "status": "UNVERIFIED",
                    "passed": False,
                    "reason": "INSUFFICIENT_COUNCIL_SIZE: Council requires at least 2 independent perspectives for multi-agent adjudication."
                }
            })

        for i, debater in enumerate(debaters_outputs):
            name = debater.get("name", f"Debater_{i+1}")
            thesis = debater.get("thesis", "")
            theses.append(thesis)
            claim = debater.get("claim", "")
            file_ref = debater.get("file")
            start_line = debater.get("start_line", 1)
            end_line = debater.get("end_line", 1)
            debater_status = debater.get("status", "PARSED")

            if debater_status == "UNVERIFIED" or not file_ref or not claim or not thesis:
                missing_res = {
                    "status": "UNVERIFIED",
                    "passed": False,
                    "reason": f"EVIDENCE_RECEIPT_UNVERIFIED: {debater.get('parse_errors', ['Missing mandatory receipt fields'])}"
                }
                audit_trail["evidence_audits"].append({
                    "debater": name,
                    "claim": claim or thesis or "UNSPECIFIED",
                    "citation": f"{file_ref}:{start_line}-{end_line}" if file_ref else "MISSING",
                    "result": missing_res
                })
                audit_trail["gate_passed"] = False
            else:
                ev_res = self.evidence_validator.verify_grounding(claim, file_ref, start_line, end_line)
                audit_trail["evidence_audits"].append({
                    "debater": name,
                    "claim": claim,
                    "citation": f"{file_ref}:{start_line}-{end_line}",
                    "result": ev_res
                })
                if not ev_res["passed"]:
                    audit_trail["gate_passed"] = False
                else:
                    verified_evidence_texts.append(claim)

        # 2. Audit anti-slop and false atomicity in draft report
        slop_check = self.evaluation_gate.audit_anti_slop(draft_resolution_report)
        safety_check = self.evaluation_gate.audit_atomicity_and_rollback(draft_resolution_report)
        
        # 3. Audit dissent preservation (against sneaky consensus)
        dissent_check = self.dissent_gate.evaluate_dissent_handling(theses, draft_resolution_report)

        # 4. Audit evidence completeness (checking for ungrounded numbers like +300% or 85% CPU)
        quant_check = self.evaluation_gate.audit_quantitative_assertions(draft_resolution_report, verified_evidence_texts)

        audit_trail["slop_audit"] = slop_check
        audit_trail["safety_audit"] = safety_check
        audit_trail["dissent_audit"] = dissent_check
        audit_trail["quantitative_audit"] = quant_check

        if not slop_check["passed"] or not safety_check["passed"] or not dissent_check["passed"] or not quant_check["passed"]:
            audit_trail["gate_passed"] = False

        # 5. FAIL-CLOSED RATIFICATION GATE
        if not audit_trail["gate_passed"]:
            audit_trail["status"] = "RATIFICATION_BLOCKED"
            reasons = []
            
            # Evidence breakdown
            if any(ev["result"].get("status") == "CONTRADICTED" for ev in audit_trail["evidence_audits"]):
                reasons.append("Contradicted-Citations")
            if any(ev["result"].get("status") == "INSUFFICIENT" for ev in audit_trail["evidence_audits"]):
                reasons.append("Insufficient-Evidence")
            if any(ev["result"].get("status") == "UNVERIFIED" for ev in audit_trail["evidence_audits"]):
                reasons.append("Unverified/Missing-Citations")
            
            # Report audits
            if not slop_check["passed"]: reasons.append("Slop/Pseudo-math")
            if not safety_check["passed"]: reasons.append("Safety/False-atomicity")
            if not dissent_check["passed"]: reasons.append("Sneaky-consensus/Dissent-missing")
            if not quant_check["passed"]: reasons.append(f"Ungrounded-metrics: {quant_check['violations']}")
            
            audit_trail["final_action"] = f"HALTED: Council resolution rejected by independent evaluation gate ({', '.join(reasons)}). Revision required."
            return audit_trail

        # 6. APPROVED & RATIFIED
        audit_trail["status"] = "RATIFIED"
        audit_trail["final_action"] = "RELEASED: Council decision passed all verification gates."
        audit_trail["ratified_report"] = draft_resolution_report
        return audit_trail
