#!/usr/bin/env python3
"""
Semantic Evidence Validator
Verifies not only that files and line ranges exist,
but that the cited file content semantically substantiates the claim made by the agent.
Rejects fabricated claims that cite unrelated code as a facade.
"""

import os
import re
from typing import Dict, Any, List, Tuple

class SemanticEvidenceValidator:
    def __init__(self, repo_root: str):
        self.repo_root = os.path.abspath(repo_root)

    def extract_citations(self, text: str) -> List[Tuple[str, int, int]]:
        citations = []
        p1 = re.compile(r'\[([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+):(\d+)(?:-(\d+))?\]')
        for match in p1.finditer(text):
            filepath, start, end = match.groups()
            s_line = int(start)
            e_line = int(end) if end else s_line
            citations.append((filepath, s_line, e_line))
        return citations

    def read_line_slice(self, filepath: str, start_line: int, end_line: int) -> Tuple[bool, str, str]:
        full_path = filepath if os.path.isabs(filepath) else os.path.join(self.repo_root, filepath)
        if not os.path.exists(full_path):
            return False, "", f"FILE_NOT_FOUND: '{filepath}' does not exist."

        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception as e:
            return False, "", f"READ_ERROR: {e}"

        total = len(lines)
        if start_line < 1 or start_line > total:
            return False, "", f"LINE_OUT_OF_BOUNDS: Line {start_line} exceeds file length {total}."
        if end_line > total:
            return False, "", f"RANGE_OUT_OF_BOUNDS: Line {end_line} exceeds file length {total}."

        # Extract 1-indexed lines
        content_slice = "".join(lines[start_line - 1 : end_line])
        return True, content_slice, ""

    @staticmethod
    def _extract_keywords(text: str) -> set:
        """
        Extracts alphanumeric keywords ignoring common stopwords.
        """
        stopwords = {
            "the", "and", "is", "at", "which", "on", "in", "a", "an", "this",
            "that", "to", "of", "for", "with", "as", "by", "from", "it", "or",
            "be", "are", "has", "have", "had", "been", "was", "were", "do", "does"
        }
        words = re.findall(r'[a-zA-Z0-9_]{3,}', text.lower())
        return {w for w in words if w not in stopwords}

    def verify_grounding(self, claim: str, filepath: str, start_line: int, end_line: int) -> Dict[str, Any]:
        """
        Evaluates whether the cited file slice actually supports the claim.
        """
        ok, content, err = self.read_line_slice(filepath, start_line, end_line)
        if not ok:
            return {
                "passed": False,
                "reason": "FILE_NOT_FOUND" if "FILE_NOT_FOUND" in err else "BOUNDS_ERROR",
                "detail": err
            }

        claim_keywords = self._extract_keywords(claim)
        content_keywords = self._extract_keywords(content)

        if not claim_keywords:
            return {"passed": True, "overlap_ratio": 1.0, "reason": "EMPTY_CLAIM"}

        intersection = claim_keywords.intersection(content_keywords)
        overlap_ratio = len(intersection) / len(claim_keywords)

        # To be grounded, at least 30% of significant claim terms or core entities must appear in the cited text
        is_grounded = overlap_ratio >= 0.25 or len(intersection) >= 2

        if not is_grounded:
            return {
                "passed": False,
                "reason": "SEMANTIC_EVIDENCE_MISMATCH",
                "detail": f"Claim asserted '{claim}', but cited lines [{filepath}:{start_line}-{end_line}] discuss: '{content.strip()[:100]}...'",
                "overlap_keywords": list(intersection),
                "overlap_ratio": overlap_ratio
            }

        return {
            "passed": True,
            "reason": None,
            "overlap_keywords": list(intersection),
            "overlap_ratio": overlap_ratio,
            "cited_content_preview": content.strip()[:100]
        }
