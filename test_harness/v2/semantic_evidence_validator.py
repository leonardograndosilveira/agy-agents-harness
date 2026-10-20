#!/usr/bin/env python3
"""
Semantic Evidence Validator (Hardened P1)
Verifies claim-level provenance with immutable source references and defensible verification.
Distinguishes four distinct evidence states:
1. SUPPORTED: Direct source support established with aligned predicates, units, and conditions.
2. CONTRADICTED: Source slice directly conflicts with claim (polarity, negation, condition, or direction flip).
3. INSUFFICIENT: Related evidence does not establish claim (default when inconclusive).
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
            "our", "we", "they", "their", "should", "could", "would", "about",
            "configured", "including", "specified", "shows", "states", "defines",
            "contains", "council", "moderator", "debater", "agent", "system",
            "file", "line", "lines", "implementation", "function", "method", "class", "module"
        }
        words = re.findall(r'[a-zA-Z0-9_\-]{3,}', text.lower())
        return {w for w in words if w not in stopwords}

    @staticmethod
    def _extract_metrics(text: str) -> List[str]:
        """Extracts percentages, rates, units, and standalone numerical values with exact units."""
        patterns = [
            r'[+-]?\d+(?:\.\d+)?%',
            r'\b\d+(?:\.\d+)?\s*(?:gb/s|mb/s|kb/s|req/s|qps|iops|ms|s|sec|gb|mb|kb|cpu|ram)\b',
            r'\b\d+(?:\.\d+)?\s*(?:k|m)\b',
            r'\b\d+\b'
        ]
        results = []
        for pat in patterns:
            for match in re.finditer(pat, text, re.IGNORECASE):
                results.append(match.group(0).strip().lower())
        return list(dict.fromkeys(results))

    def verify_grounding(self, claim: str, filepath: str, start_line: int, end_line: int) -> Dict[str, Any]:
        """
        Evaluates whether the cited source slice genuinely substantiates the claim.
        Returns one of four states:
        - SUPPORTED: Direct source support established.
        - CONTRADICTED: Source directly conflicts with claim (polarity, negation, condition, or direction flip).
        - INSUFFICIENT: Related evidence does not establish claim (default when inconclusive).
        - UNVERIFIED: Citation missing, unreadable, out of bounds, or nonexistent.
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

        # 1. Contradiction & Reversal Detection:
        CONTRADICTION_PAIRS = [
            ({"passed", "pass", "succeeded", "succeed", "success"}, {"failed", "fail", "failure", "violated", "exceeded limits", "degraded"}),
            ({"higher", "greater", "faster", "more", "superior", "exceeds", "increase"}, {"lower", "less", "slower", "inferior", "worse", "decrease"}),
            ({"enabled", "enable", "activated", "allowed", "supported", "permits"}, {"disabled", "disable", "prohibited", "denied", "blocked", "forbidden", "unsupported"}),
            ({"safe", "optimal", "reliable", "consistent", "atomic"}, {"vulnerable", "unsafe", "flawed", "hazard", "unreliable", "stale", "inconsistent", "false atomicity"}),
            ({"without", "unconditionally"}, {"only when", "only if", "requires", "conditional upon", "depends on"}),
            ({"causes", "provokes", "triggers failure"}, {"prevents", "avoids", "eliminates", "protects against"})
        ]

        for set_a, set_b in CONTRADICTION_PAIRS:
            a_in_claim = any(re.search(r'\b' + re.escape(w) + r'\b', claim_lower) for w in set_a)
            b_in_source = any(re.search(r'\b' + re.escape(w) + r'\b', content_lower) for w in set_b)
            if a_in_claim and b_in_source:
                return {
                    "status": "CONTRADICTED",
                    "passed": False,
                    "provenance_hash": provenance_hash,
                    "reason": "PROPOSITION_CONTRADICTED",
                    "detail": "Claim asserts proposition directly contradicted by cited source slice.",
                    "cited_slice_preview": content.strip()[:140]
                }
            
            b_in_claim = any(re.search(r'\b' + re.escape(w) + r'\b', claim_lower) for w in set_b)
            a_in_source = any(re.search(r'\b' + re.escape(w) + r'\b', content_lower) for w in set_a)
            if b_in_claim and a_in_source:
                return {
                    "status": "CONTRADICTED",
                    "passed": False,
                    "provenance_hash": provenance_hash,
                    "reason": "PROPOSITION_CONTRADICTED",
                    "detail": "Claim asserts proposition directly contradicted by cited source slice.",
                    "cited_slice_preview": content.strip()[:140]
                }

        # Check explicit negation markers (must not, cannot, never, not)
        negation_markers = ["not", "never", "must not", "cannot"]
        for neg in negation_markers:
            if re.search(r'\b' + re.escape(neg) + r'\b', content_lower):
                claim_has_neg = any(re.search(r'\b' + re.escape(n) + r'\b', claim_lower) for n in negation_markers)
                if not claim_has_neg:
                    if any(aff in claim_lower for aff in ["rely on", "relies on", "provides", "guarantees", "is optimal", "achieves", "safe"]):
                        return {
                            "status": "CONTRADICTED",
                            "passed": False,
                            "provenance_hash": provenance_hash,
                            "reason": "PROPOSITION_CONTRADICTED",
                            "detail": f"Source slice explicitly contains negation ('{neg}') contradicting the asserted claim.",
                            "cited_slice_preview": content.strip()[:140]
                        }

        # 2. Quantitative Metric Alignment Verification
        claim_metrics = self._extract_metrics(claim)
        content_metrics = self._extract_metrics(content)

        if claim_metrics:
            missing_metrics = []
            for m in claim_metrics:
                if not re.search(r'(?:\b|\A)' + re.escape(m) + r'(?:\b|\Z)', content_lower):
                    missing_metrics.append(m)
            if missing_metrics:
                return {
                    "status": "INSUFFICIENT",
                    "passed": False,
                    "provenance_hash": provenance_hash,
                    "reason": "QUANTITATIVE_MISMATCH",
                    "detail": f"Claim asserts quantitative metric(s) {missing_metrics} that do not appear in cited source slice.",
                    "cited_slice_preview": content.strip()[:140]
                }

        # 3. Direct Substantive Grounding Check
        claim_keywords = self._extract_keywords(claim)
        content_keywords = self._extract_keywords(content)
        shared_keywords = claim_keywords.intersection(content_keywords)

        if not claim_keywords:
            return {
                "status": "INSUFFICIENT",
                "passed": False,
                "reason": "EMPTY_CLAIM",
                "detail": "Claim contains no identifiable technical proposition."
            }

        # Check for ungrounded technical terms introduced in claim
        missing_technical_terms = [w for w in claim_keywords if w not in content_keywords]
        
        if len(claim_keywords) >= 4 and len(missing_technical_terms) / len(claim_keywords) > 0.25:
            return {
                "status": "INSUFFICIENT",
                "passed": False,
                "provenance_hash": provenance_hash,
                "reason": "EVIDENCE_INSUFFICIENT",
                "detail": f"Source does not substantiate key propositions: {missing_technical_terms[:5]}",
                "cited_slice_preview": content.strip()[:140]
            }

        # Verbatim or high-fidelity phrase match
        clean_content = re.sub(r'\s+', ' ', content_lower).strip()
        clean_claim = re.sub(r'\s+', ' ', claim_lower).strip()
        clean_content_stripped = re.sub(r'#\s*(?:line\s*\d+:?\s*)?', '', clean_content).strip()

        is_direct_substring = (clean_claim in clean_content) or (clean_claim in clean_content_stripped)
        overlap_ratio = len(shared_keywords) / len(claim_keywords)

        # To be SUPPORTED: direct substring or complete keyword support without ungrounded terms
        if is_direct_substring or (overlap_ratio >= 0.85 and len(missing_technical_terms) == 0):
            return {
                "status": "SUPPORTED",
                "passed": True,
                "provenance_hash": provenance_hash,
                "shared_keywords": list(shared_keywords),
                "overlap_ratio": overlap_ratio,
                "cited_slice_preview": content.strip()[:140]
            }

        # Default to INSUFFICIENT when semantic support cannot be deterministically proven
        return {
            "status": "INSUFFICIENT",
            "passed": False,
            "provenance_hash": provenance_hash,
            "reason": "EVIDENCE_INSUFFICIENT",
            "detail": f"Related entities present but evidence does not deterministically establish claim. Overlap: {overlap_ratio:.2f}",
            "cited_slice_preview": content.strip()[:140]
        }
