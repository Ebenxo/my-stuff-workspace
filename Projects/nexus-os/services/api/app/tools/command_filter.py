"""Assess and filter commands before they can run. Hard denials are final; everything else is HIGH
and always needs a person, who sees the exact argument list."""

from __future__ import annotations

import re
from pathlib import PurePath

from app.core.risk import RiskLevel
from app.permissions.policy import RiskAssessment

DENY_PROGRAMS = frozenset(
    {
        "sudo",
        "su",
        "doas",
        "pkexec",
        "runas",
        "chown",
        "chgrp",
        "mkfs",
        "fdisk",
        "parted",
        "dd",
        "shutdown",
        "reboot",
        "halt",
        "poweroff",
        "init",
        "systemctl",
        "service",
        "crontab",
        "at",
        "batch",
        "passwd",
        "useradd",
        "userdel",
        "usermod",
        "groupadd",
        "visudo",
        "mount",
        "umount",
        "iptables",
        "ufw",
        "nft",
        "format",
        "diskpart",
        "reg",
        "regedit",
        "bcdedit",
        "schtasks",
        "sc",
        "netsh",
        "wmic",
        "cipher",
        "vssadmin",
        "takeown",
        "icacls",
        "launchctl",
        "kill",
        "killall",
        "pkill",
        "taskkill",
        "nc",
        "ncat",
        "netcat",
        "socat",
        "ssh",
        "scp",
        "sftp",
        "telnet",
        "insmod",
        "modprobe",
        "setcap",
        "chroot",
        "nsenter",
        "docker",
        "podman",
        "kubectl",
    }
)
SHELLS = frozenset(
    {"sh", "bash", "zsh", "fish", "dash", "ksh", "csh", "tcsh", "cmd", "powershell", "pwsh", "wsl"}
)
CATASTROPHIC = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\brm\s+(-[a-z]*\s+)*-[a-z]*[rf][a-z]*\s+(-[a-z]+\s+)*(/|~|\*|\.|\$HOME|/\*)(\s|$)",
        r":\(\)\s*\{.*\};\s*:",
        r">\s*/dev/(sd|nvme|hd)[a-z0-9]*",
        r"\bmkfs(\.\w+)?\b",
        r"\bdd\s+if=",
        r"\bchmod\s+-R\s+[0-7]{3,4}\s+/(\s|$)",
        r"\b(del|erase)\s+/[sq]\b.*[a-z]:\\",
        r"\b(rd|rmdir)\s+/s\b.*[a-z]:\\",
        r"\bformat\s+[a-z]:",
        r"\b(curl|wget|fetch)\b[^\n|;]*\|\s*(sudo\s+)?(ba|z|da)?sh\b",
        r"\bbase64\s+(-d|--decode)[^\n|]*\|\s*(ba|z)?sh\b",
        r"/dev/(tcp|udp)/",
        r"\bnc\b[^\n]*\s-e\b",
        r"\beval\s+[\"'`$]",
        r"\$\((curl|wget)",
        r"`(curl|wget)",
    )
]
_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")


def program_name(argv0: str) -> str:
    name = PurePath(argv0.replace("\\", "/")).name.lower()
    return name[:-4] if name.endswith(".exe") else name


def assess_command(
    argv: list[str], *, shell_text: str | None = None, network: bool = False, cwd: str = "files"
) -> RiskAssessment:
    """Risk for ``run_command``. ``shell_text`` is set when the command runs through a shell."""
    if not argv or not argv[0].strip():
        return RiskAssessment(deny_reason="No command was given.")
    prog = program_name(argv[0])
    text = shell_text if shell_text is not None else " ".join(argv)

    if shell_text is None:
        if prog in DENY_PROGRAMS:
            return RiskAssessment(
                deny_reason=f"'{prog}' is blocked: it can change the system or other users' data."
            )
        if prog in SHELLS:
            return RiskAssessment(
                deny_reason=f"Start '{prog}' by setting shell=true and giving the command text, so it is reviewed as a shell command."
            )
    for pattern in CATASTROPHIC:
        if pattern.search(text):
            return RiskAssessment(
                deny_reason="That command matches a known destructive or remote-execution pattern and is blocked."
            )
    if shell_text is not None:
        for token in re.split(r"[;&|\n`]|\$\(", shell_text):
            first = token.strip().split(" ", 1)[0] if token.strip() else ""
            if first and program_name(first) in DENY_PROGRAMS:
                return RiskAssessment(
                    deny_reason=f"'{program_name(first)}' is blocked inside shell commands."
                )

    outside = [
        a
        for a in argv[1:]
        if a.startswith(("/", "~")) or _DRIVE.match(a) or ".." in a.replace("\\", "/").split("/")
    ]
    level = RiskLevel.VERY_HIGH if network else RiskLevel.HIGH
    note = "Network access is ON." if network else "Network access is off."
    if outside:
        note += f" It refers to paths outside the project: {', '.join(outside[:3])}."
    what = f"shell command `{text}`" if shell_text is not None else f"`{' '.join(argv)}`"
    return RiskAssessment(level=level, always_ask=True, impact=f"Runs {what} in {cwd}/. {note}")
