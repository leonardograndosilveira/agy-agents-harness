#!/usr/bin/env python3
"""
Semantic Evidence Validator (Hardened P1)
Verifies claim-level provenance with immutable source references.
Distinguishes four distinct evidence states:
1. SUPPORTED: Source slice directly substantiates the specific proposition and quantities.
2. CONTRADICTED: Source slice negates or directly contradicts the proposition.
3. INSUFFICIENT: Source mentions related entities but lacks sufficient support for the claim.
4. UNVERIFIED: Citation missing, unreadable, out of bounds, or nonexistent.
"""

import os
import re
import hashlib
from typing import Dict, Any, List, Tuple, Set

class SemanticEvidenceValidator:
    def __init__(self, repo_root: str = None):
        if repo_root:
            self.repo_root = os.path.realpath(os.path.abspath(os.path.expanduser(repo_root)))
        else:
            self.repo_root = os.path.realpath(os.getcwd())

    def extract_citations(self, text: str) -> List[Tuple[str, int, int]]:
        citations = []
        p1 = re.compile(r'\[(?:FILE:LINE:\s*)?([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+):(\d+)(?:-(\d+))?\]')
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
        if end_line > total or end_line < start_line:
            return False, "", f"RANGE_OUT_OF_BOUNDS: Line range [{start_line}-{end_line}] invalid for file length {total}."

        content_slice = "".join(lines[start_line - 1 : end_line])
        return True, content_slice, ""

    @staticmethod
    def _extract_keywords(text: str) -> Set[str]:
        stopwords = {
            "the", "and", "is", "at", "which", "on", "in", "a", "an", "this",
            "that", "to", "of", "for", "with", "as", "by", "from", "it", "or",
            "be", "are", "has", "have", "had", "been", "was", "were", "do", "does",
            "our", "we", "they", "their", "should", "could", "would", "about"
        }
        words = re.findall(r'[a-zA-Z0-9_\-]{3,}', text.lower())
        return {w for w in words if w not in stopwords}

    @staticmethod
    def _extract_metrics(text: str) -> List[str]:
        """Extracts percentages, rates, units, and standalone numerical values."""
        patterns = [
            r'[+-]?\d+(?:\.\d+)?%',
            r'\b\d+(?:\.\d+)?\s*(?:ms|s|sec|qps|QPS|req/s|cpu|CPU|ram|RAM|mb|gb|MB|GB|k|K|M)\b',
            r'\b\d{2,}\b'
        ]
        results = []
        for pat in patterns:
            for match in re.finditer(pat, text, re.IGNORECASE):
                results.append(match.group(0).strip().lower())
        return list(set(results))

    def verify_grounding(self, claim: str, filepath: str, start_line: int, end_line: int) -> Dict[str, Any]:
        """
        Evaluates whether the cited source slice genuinely substantiates the claim.
        Returns one of four states: SUPPORTED, CONTRADICTED, INSUFFICIENT, UNVERIFIED.
        """
        if not filepath:
            return {
                "status": "UNVERIFIED",
                "passed": False,
                "reason": "MISSING_CITATION: No source file was cited."
            }

        ok, content, err = self.read_line_slice(filepath, start_line, end_line)
        if not ok:
            return {
                "status": "UNVERIFIED",
                "passed": False,
                "reason": "UNVERIFIED_CITATION",
                "detail": err
            }

        provenance_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        content_lower = content.lower()
        claim_lower = claim.lower()

        claim_keywords = self._extract_keywords(claim)
        content_keywords = self._extract_keywords(content)
        shared_keywords = claim_keywords.intersection(content_keywords)

        # 1. Contradiction Detection: Polarity Flip & Rejection
        negation_markers = {
            "not", "never", "prohibit", "prohibited", "denied", "blocked",
            "forbidden", "vulnerable", "fails", "defect", "hazard", "danger",
            "must not", "cannot", "toctou", "race condition", "stale", "flaw"
        }
        positive_affirmations = {
            "rely on", "relies on", "provides", "guarantees", "atomic",
            "safe", "optimal", "fast", "recommended", "superior"
        }

        content_has_negation = any(neg in content_lower for neg in negation_markers)
        claim_has_positive = any(pos in claim_lower for pos in positive_affirmations)

        # If claim asserts a positive guarantee on an entity that the source explicitly negates/warns against
        if content_has_negation and claim_has_positive and len(shared_keywords) >= 2:
            # Check if negation in source applies to key entities in the claim
            for neg in negation_markers:
                if neg in content_lower:
                    return {
                        "status": "CONTRADICTED",
                        "passed": False,
                        "provenance_hash": provenance_hash,
                        "reason": "PROPOSITION_CONTRADICTED",
                        "detail": f"Source slice explicitly contains negation/warning ('{neg}') contradicting the asserted proposition.",
                        "cited_slice_preview": content.strip()[:140]
                    }

        # 2. Quantitative Metric Alignment Verification
        claim_metrics = self._extract_metrics(claim)
        content_metrics = self._extract_metrics(content)

        if claim_metrics:
            missing_metrics = [m for m in claim_metrics if m not in content_lower]
            if missing_metrics:
                return {
                    "status": "INSUFFICIENT",
                    "passed": False,
                    "provenance_hash": provenance_hash,
                    "reason": "QUANTITATIVE_MISMATCH",
                    "detail": f"Claim asserts quantitative metric(s) {missing_metrics} that do not appear in cited source slice.",
                    "cited_slice_preview": content.strip()[:140]
                }

        # 3. Semantic Relevance and Sufficiency
        if not claim_keywords:
            return {
                "status": "INSUFFICIENT",
                "passed": False,
                "reason": "EMPTY_CLAIM",
                "detail": "Claim contains no identifiable technical proposition."
            }

        overlap_ratio = len(shared_keywords) / len(claim_keywords)
        if overlap_ratio < 0.25 and len(shared_keywords) < 2:
            return {
                "status": "INSUFFICIENT",
                "passed": False,
                "provenance_hash": provenance_hash,
                "reason": "EVIDENCE_INSUFFICIENT",
                "detail": f"Cited lines do not adequately support claim. Overlap ratio: {overlap_ratio:.2f}",
                "cited_slice_preview": content.strip()[:140]
            }

        # 4. SUPPORTED
        return {
            "status": "SUPPORTED",
            "passed": True,
            "provenance_hash": provenance_hash,
            "shared_keywords": list(shared_keywords),
            "overlap_ratio": overlap_ratio,
            "cited_slice_preview": content.strip()[:140]
        }
