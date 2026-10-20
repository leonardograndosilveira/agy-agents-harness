# Security Exposure Audit & History Remediation Report

**Date:** 2026-10-20  
**Repository:** [agy-agents-harness](https://github.com/leonardograndosilveira/agy-agents-harness)  
**Author:** Council Security & Verification Engineering  
**Branch:** `fix/security-and-e2e-gaps`  

---

## 1. Executive Summary

An independent security review identified that prior commits in the public Git history tracked runtime execution logs, local machine paths, Python bytecode (`.pyc`), and sensitive local daemon authorization credentials. While commit `8381792` purged these files from the current working tree, Git commit objects remain reachable in the repository history.

Per standard engineering and security guidelines, **no destructive history rewrites (such as `git push --force`) are performed automatically without explicit stakeholder review and approval**. This document outlines the exact exposure, risk analysis, and actionable remediation pathways.

---

## 2. Leaked Artifacts & Historical Commits

### Commit `d11c4e62619afad41a7e528a605f09477e0b507e`
*Date: Tue Oct 20 11:28:49 2026 -0300*

Tracked files introduced:
1. `test_harness/council_runtime/hook_execution.log`
2. `test_harness/council_runtime/live_hook.log`
3. `test_harness/council_runtime/__pycache__/council_orchestrator.cpython-312.pyc`

#### Specific Exposed Data (Redacted):
- **Local Daemon Auth Token:**
  `token: "[REDACTED_LOCAL_STATIC_TOKEN_SHA256]"`
- **Ingest Key:**
  `ingest_key: "[REDACTED_LOCAL_INGEST_KEY_UUID]"`
- **Local Daemon Endpoint:**
  `http://127.0.0.1:49374/hook?event=pre-tool-use&agent=antigravity-cli&ingest_key=...`
- **Absolute Host Paths:**
  `/home/allcance/.gemini/antigravity/...`
  `/home/allcance/.local/share/ai-memory/...`

### Commits `81b11d2` & `8a9955c`
Tracked compiled Python bytecode (`.pyc`) for:
- `evaluation_gate.cpython-312.pyc`
- `evidence_validator.cpython-312.pyc`
- `execution_safety_validator.cpython-312.pyc`
- `path_confinement_validator.cpython-312.pyc`
- `process_group_runner.cpython-312.pyc`
- `runtime_interceptor.cpython-312.pyc`
- `semantic_evaluation_gate.cpython-312.pyc`
- `semantic_evidence_validator.cpython-312.pyc`
- `regression_suite.cpython-312.pyc`

---

## 3. Threat Assessment & Blast Radius

| Asset Exposed | Scope | Blast Radius | Severity |
| :--- | :--- | :--- | :--- |
| `ai-memory` auth token & ingest key | Localhost daemon (`127.0.0.1:49374`) | Unauthenticated processes on the same host could send unverified events to the local memory daemon. No external cloud infrastructure access. | **Medium** |
| Local machine username & paths | Environment metadata | Information disclosure of local directory conventions. | **Low** |
| Compiled bytecode (`.pyc`) | Python bytecode | Reversible binary representation of internal logic prior to cleanup. | **Low** |

---

## 4. Remediation Options & Action Plan

### Step 1: Immediate Token Invalidation (Recommended)
Rotate the static token and ingest key for the local `ai-memory` hook spool daemon. Generating fresh keys locally renders the exposed historical credentials completely invalid.

### Step 2: History Cleanup Options (Requires Approval)

#### Option A: Surgical Git History Rewrite via `git-filter-repo` (Recommended if rewrite approved)
Purge `*.log` and `*.pyc` files from all reachable history while preserving commit messages:
```bash
# Example rewrite commands (DO NOT EXECUTE WITHOUT USER CONFIRMATION):
git filter-repo --invert-paths \
  --path-glob '*.log' \
  --path-glob '*.pyc' \
  --path-glob '*__pycache__*' \
  --force
git push origin --force --all
```
*Trade-off:* Modifies commit hashes; requires anyone who cloned the repository to reset their local branch.

#### Option B: Clean Forward History (Safe, Non-Destructive)
Retain the current history structure where files were already untracked in `8381792`.
- Rotate the local tokens immediately.
- Enforce strict automated secret and hygiene gates in CI to prevent any future leak.

---

## 5. Automated CI Prevention Gate

Added secret and hygiene scanning in `.github/workflows/ci.yml`:
1. **Bytecode Check:** Fails if any `.pyc` or `__pycache__` file is committed.
2. **Log File Check:** Fails if any `.log` file is committed.
3. **Secret Pattern Scanning:** Scans all new commits for token strings, auth headers, and hardcoded sensitive credentials.
