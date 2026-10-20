#!/usr/bin/env python3
"""
Enforced Council Orchestrator
Wired directly into the independent Evaluation Gate.
Demonstrates Fail-Closed Behavior: if evidence verification fails or false consensus is detected,
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
    def __init__(self, workspace_root: str, agents_root: str):
        self.workspace_root = workspace_root
        self.agents_root = agents_root
        self.evidence_validator = SemanticEvidenceValidator(agents_root)
        self.evaluation_gate = EvaluationGate(agents_root)
        self.dissent_gate = SemanticEvaluationGate()

    def process_council_turn(self, 
                             problem_statement: str, 
                             debaters_outputs: List[Dict[str, Any]], 
                             draft_resolution_report: str) -> Dict[str, Any]:
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
        for i, debater in enumerate(debaters_outputs):
            name = debater.get("name", f"Debater_{i+1}")
            thesis = debater.get("thesis", "")
            theses.append(thesis)
            claim = debater.get("claim", "")
            file_ref = debater.get("file")
            start_line = debater.get("start_line", 1)
            end_line = debater.get("end_line", 1)

            if file_ref:
                ev_res = self.evidence_validator.verify_grounding(claim, file_ref, start_line, end_line)
                audit_trail["evidence_audits"].append({
                    "debater": name,
                    "claim": claim,
                    "citation": f"{file_ref}:{start_line}-{end_line}",
                    "result": ev_res
                })
                if not ev_res["passed"]:
                    audit_trail["gate_passed"] = False

        # 2. Audit anti-slop and false atomicity in draft report
        slop_check = self.evaluation_gate.audit_anti_slop(draft_resolution_report)
        safety_check = self.evaluation_gate.audit_atomicity_and_rollback(draft_resolution_report)
        
        # 3. Audit dissent preservation (against sneaky consensus)
        dissent_check = self.dissent_gate.evaluate_dissent_handling(theses, draft_resolution_report)

        audit_trail["slop_audit"] = slop_check
        audit_trail["safety_audit"] = safety_check
        audit_trail["dissent_audit"] = dissent_check

        if not slop_check["passed"] or not safety_check["passed"] or not dissent_check["passed"]:
            audit_trail["gate_passed"] = False

        # 4. FAIL-CLOSED RATIFICATION GATE
        if not audit_trail["gate_passed"]:
            audit_trail["status"] = "RATIFICATION_BLOCKED"
            audit_trail["final_action"] = "HALTED: Council resolution rejected by independent evaluation gate. Revision required."
            return audit_trail

        # 5. APPROVED & RATIFIED
        audit_trail["status"] = "RATIFIED"
        audit_trail["final_action"] = "RELEASED: Council decision passed all verification gates."
        audit_trail["ratified_report"] = draft_resolution_report
        return audit_trail
