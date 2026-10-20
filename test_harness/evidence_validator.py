#!/usr/bin/env python3
"""
Evidence Validator
Verifies citations, detects hallucinated file:line references,
and validates that technical claims are backed by actual filesystem ground truth.
"""

import os
import re
from typing import Dict, List, Tuple, Any

class CitationError(Exception):
    pass

class EvidenceValidator:
    def __init__(self, repo_root: str):
        self.repo_root = os.path.abspath(repo_root)

    def extract_citations(self, text: str) -> List[Tuple[str, int, int]]:
        """
        Extracts citations in formats:
        - [file.py:42]
        - [path/to/file.py:10-25]
        - [file:///abs/path/file.py#L10-L20]
        Returns list of (filepath, start_line, end_line).
        """
        citations = []
        # Match [path/to/file.ext:line] or [path/to/file.ext:start-end]
        p1 = re.compile(r'\[([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+):(\d+)(?:-(\d+))?\]')
        for match in p1.finditer(text):
            filepath, start, end = match.groups()
            s_line = int(start)
            e_line = int(end) if end else s_line
            citations.append((filepath, s_line, e_line))

        # Match file:///path/file.ext#Lstart-Lend
        p2 = re.compile(r'\[.*?\]\(file://([a-zA-Z0-9_\-./]+)(?:#L(\d+)(?:-L(\d+))?)?\)')
        for match in p2.finditer(text):
            filepath, start, end = match.groups()
            s_line = int(start) if start else 1
            e_line = int(end) if end else s_line
            citations.append((filepath, s_line, e_line))

        return citations

    def verify_citation(self, rel_or_abs_path: str, start_line: int, end_line: int) -> Tuple[bool, str]:
        """
        Checks if file exists and cited line range is within file boundaries.
        """
        if os.path.isabs(rel_or_abs_path):
            full_path = rel_or_abs_path
        else:
            full_path = os.path.join(self.repo_root, rel_or_abs_path)

        if not os.path.exists(full_path):
            return False, f"FILE_NOT_FOUND: '{rel_or_abs_path}' does not exist on disk."

        try:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except Exception as e:
            return False, f"READ_ERROR: Could not read '{rel_or_abs_path}': {e}"

        total_lines = len(lines)
        if start_line < 1 or start_line > total_lines:
            return False, f"LINE_OUT_OF_BOUNDS: Line {start_line} does not exist in '{rel_or_abs_path}' (file has {total_lines} lines)."
        if end_line < start_line or end_line > total_lines:
            return False, f"RANGE_OUT_OF_BOUNDS: Range {start_line}-{end_line} invalid for file with {total_lines} lines."

        return True, f"VERIFIED: {rel_or_abs_path}:{start_line}-{end_line} (File has {total_lines} lines)"

    def validate_receipt(self, receipt_text: str) -> Dict[str, Any]:
        """
        Validates an Evidence Receipt. Rejects hallucinated citations.
        """
        citations = self.extract_citations(receipt_text)
        results = {
            "total_citations": len(citations),
            "verified": [],
            "failed": [],
            "has_unverified_tag": "[UNVERIFIED HYPOTHESIS]" in receipt_text,
            "passed": True
        }

        for path, s, e in citations:
            ok, msg = self.verify_citation(path, s, e)
            if ok:
                results["verified"].append({"citation": f"{path}:{s}-{e}", "message": msg})
            else:
                results["failed"].append({"citation": f"{path}:{s}-{e}", "error": msg})
                results["passed"] = False

        # If claim asserts empirical evidence but citations failed, fail the receipt
        if results["failed"]:
            results["passed"] = False

        return results

if __name__ == "__main__":
    validator = EvidenceValidator(os.getcwd())
    sample = "As seen in [council-moderator.md:15-30], the moderator coordinates..."
    print(validator.validate_receipt(sample))
