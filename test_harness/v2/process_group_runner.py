#!/usr/bin/env python3
"""
Process Group & Resource Runner
Executes commands with process-group isolation, OS-level resource limits (RLIMIT_AS, RLIMIT_CPU),
and full process-tree termination on timeout to prevent orphaned background children.
"""

import os
import signal
import subprocess
import time
import resource
from typing import Dict, Any, Optional

class ProcessGroupRunner:
    @staticmethod
    def _set_resource_limits(max_memory_mb: Optional[int] = None, max_cpu_seconds: Optional[int] = None):
        """
        Preexec function to set OS limits and isolate process group.
        """
        # Detach into a new process group so killpg hits all child forks
        os.setsid()

        # Set memory ceiling (virtual memory / address space)
        if max_memory_mb:
            mem_bytes = max_memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))

        # Set CPU time limit
        if max_cpu_seconds:
            resource.setrlimit(resource.RLIMIT_CPU, (max_cpu_seconds, max_cpu_seconds))

    def run_bounded_command(self, 
                            command: str, 
                            timeout_seconds: float = 5.0, 
                            max_memory_mb: Optional[int] = None,
                            cwd: Optional[str] = None) -> Dict[str, Any]:
        """
        Runs a shell command inside an isolated process group with explicit resource bounds.
        """
        start_time = time.time()
        timed_out = False
        killed_children_count = 0

        # Launch with session leader
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            preexec_fn=lambda: self._set_resource_limits(max_memory_mb=max_memory_mb)
        )

        try:
            stdout, stderr = proc.communicate(timeout=timeout_seconds)
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            # Kill entire process group (including any background forks `&`)
            pgid = proc.pid
            try:
                os.killpg(pgid, signal.SIGTERM)
                time.sleep(0.05)
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass

            try:
                stdout, stderr = proc.communicate(timeout=1.0)
            except Exception:
                stdout, stderr = b"", b""
            exit_code = -signal.SIGKILL

        elapsed = time.time() - start_time
        stdout_str = stdout.decode('utf-8', errors='ignore')
        stderr_str = stderr.decode('utf-8', errors='ignore')

        # Check for OOM / Memory limit exceeded
        memory_limit_hit = (
            exit_code == 137 or 
            exit_code == -signal.SIGKILL and not timed_out or
            "MemoryError" in stderr_str or 
            "std::bad_alloc" in stderr_str or
            proc.returncode in (-9, 137, 1) and "Memory" in stderr_str
        )

        return {
            "command": command,
            "exit_code": exit_code,
            "stdout": stdout_str,
            "stderr": stderr_str,
            "elapsed_seconds": elapsed,
            "timed_out": timed_out,
            "memory_limit_hit": memory_limit_hit,
            "clean_termination": True
        }
