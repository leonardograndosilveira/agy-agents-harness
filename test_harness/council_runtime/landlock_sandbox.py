#!/usr/bin/env python3
"""
Linux Landlock OS-Level Filesystem Sandbox Runner
Enforces OS-level filesystem confinement for agent subprocesses without requiring root privileges.
Restricts mutating syscalls (creat, unlink, mkdir, rmdir, rename, symlink, mknod)
strictly to authorized workspace directories, leaving the rest of the filesystem immutable.
"""

import sys
import os
import ctypes
import subprocess
from typing import List, Optional

# Landlock Constants for Linux x86_64
SYS_landlock_create_ruleset = 444
SYS_landlock_add_rule = 445
SYS_landlock_restrict_self = 446
PR_SET_NO_NEW_PRIVS = 38

# Landlock Access Rights
LANDLOCK_ACCESS_FS_EXECUTE = (1 << 0)
LANDLOCK_ACCESS_FS_WRITE_FILE = (1 << 1)
LANDLOCK_ACCESS_FS_READ_FILE = (1 << 2)
LANDLOCK_ACCESS_FS_READ_DIR = (1 << 3)
LANDLOCK_ACCESS_FS_REMOVE_DIR = (1 << 4)
LANDLOCK_ACCESS_FS_REMOVE_FILE = (1 << 5)
LANDLOCK_ACCESS_FS_MAKE_CHAR = (1 << 6)
LANDLOCK_ACCESS_FS_MAKE_DIR = (1 << 7)
LANDLOCK_ACCESS_FS_MAKE_REG = (1 << 8)
LANDLOCK_ACCESS_FS_MAKE_SOCK = (1 << 9)
LANDLOCK_ACCESS_FS_MAKE_FIFO = (1 << 10)
LANDLOCK_ACCESS_FS_MAKE_BLOCK = (1 << 11)
LANDLOCK_ACCESS_FS_MAKE_SYM = (1 << 12)

LANDLOCK_ACCESS_FS_TRUNCATE = (1 << 14)

# Handled filesystem mutations for sandbox boundary (including overwrite and truncate)
ACCESS_FS_MUTATE = (
    LANDLOCK_ACCESS_FS_WRITE_FILE
    | LANDLOCK_ACCESS_FS_TRUNCATE
    | LANDLOCK_ACCESS_FS_REMOVE_DIR
    | LANDLOCK_ACCESS_FS_REMOVE_FILE
    | LANDLOCK_ACCESS_FS_MAKE_DIR
    | LANDLOCK_ACCESS_FS_MAKE_REG
    | LANDLOCK_ACCESS_FS_MAKE_SYM
    | LANDLOCK_ACCESS_FS_MAKE_FIFO
    | LANDLOCK_ACCESS_FS_MAKE_SOCK
)

class LandlockRulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]

class LandlockPathBeneathAttr(ctypes.Structure):
    _fields_ = [
        ("allowed_access", ctypes.c_uint64),
        ("parent_fd", ctypes.c_int32)
    ]

def is_landlock_supported() -> bool:
    """Checks if Landlock ABI is available on the current kernel."""
    if not sys.platform.startswith("linux"):
        return False
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        abi = libc.syscall(SYS_landlock_create_ruleset, 0, 0, (1 << 0))
        return abi >= 1
    except Exception:
        return False

def restrict_process_to_workspaces(allowed_write_workspaces: List[str]) -> bool:
    """
    Applies Landlock ruleset to the current process:
    - Mutating operations (write, truncate, create, delete, symlink, mkdir) restricted
      exclusively to allowed_write_workspaces.
    - System character devices (/dev/null, stdio) remain operational via /dev write grant.
    Once restricted, all child processes and threads inherit this restriction irreversibly.
    """
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        attr = LandlockRulesetAttr(handled_access_fs=ACCESS_FS_MUTATE)
        ruleset_fd = libc.syscall(SYS_landlock_create_ruleset, ctypes.byref(attr), ctypes.sizeof(attr), 0)
        if ruleset_fd < 0:
            return False

        # Allow write access to /dev so stdout/stderr redirection to /dev/null and tty operations work
        if os.path.exists("/dev"):
            dev_fd = os.open("/dev", os.O_PATH | os.O_CLOEXEC)
            pb_dev = LandlockPathBeneathAttr(allowed_access=LANDLOCK_ACCESS_FS_WRITE_FILE, parent_fd=dev_fd)
            libc.syscall(SYS_landlock_add_rule, ruleset_fd, 1, ctypes.byref(pb_dev), 0)
            os.close(dev_fd)

        # Allow mutation rights exclusively on permitted workspaces
        for ws in allowed_write_workspaces:
            if not os.path.exists(ws):
                continue
            ws_fd = os.open(ws, os.O_PATH | os.O_CLOEXEC)
            pb_rw = LandlockPathBeneathAttr(allowed_access=ACCESS_FS_MUTATE, parent_fd=ws_fd)
            ret_rw = libc.syscall(SYS_landlock_add_rule, ruleset_fd, 1, ctypes.byref(pb_rw), 0)
            os.close(ws_fd)
            if ret_rw < 0:
                os.close(ruleset_fd)
                return False

        # Enable PR_SET_NO_NEW_PRIVS
        if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
            os.close(ruleset_fd)
            return False

        # Restrict self
        res = libc.syscall(SYS_landlock_restrict_self, ruleset_fd, 0)
        os.close(ruleset_fd)
        return res == 0
    except Exception:
        return False

def run_sandboxed_command(cmd: str, allowed_workspaces: List[str], cwd: Optional[str] = None) -> subprocess.CompletedProcess:
    """
    Executes a shell command inside a child process restricted by Landlock OS-level sandboxing.
    """
    def preexec_fn():
        if not restrict_process_to_workspaces(allowed_workspaces):
            # Fail closed inside child before executing command
            os._exit(126)

    return subprocess.run(
        cmd,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
        preexec_fn=preexec_fn
    )

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run command inside Landlock OS sandbox")
    parser.add_argument("--workspace", action="append", required=True, help="Allowed write workspace (repeatable)")
    parser.add_argument("--cwd", default=None, help="Working directory")
    parser.add_argument("command", nargs="+", help="Command line string or tokens to execute")

    args = parser.parse_args()
    if not is_landlock_supported():
        sys.stderr.write("OS_SANDBOX_UNAVAILABLE: Landlock is not supported by kernel.\n")
        sys.exit(127)

    cmd_str = " ".join(args.command) if isinstance(args.command, list) else args.command
    res = run_sandboxed_command(cmd_str, args.workspace, cwd=args.cwd)
    sys.stdout.write(res.stdout)
    sys.stderr.write(res.stderr)
    sys.exit(res.returncode)
