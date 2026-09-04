from __future__ import annotations

from pathlib import Path
import py_compile
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED: set[Path] = set()

# Patterns are restricted to executable PowerShell source. Documentation and
# read-only search regexes are not considered executable calls.
FORBIDDEN_CALLS = [
    re.compile(r"(?im)^\s*(?:&\s*)?Enable-BitLocker\b"),
    re.compile(r"(?im)^\s*(?:&\s*)?Disable-BitLocker\b"),
    re.compile(r"(?im)^\s*(?:&\s*)?Resume-BitLocker\b"),
    re.compile(r"(?im)^\s*(?:&\s*)?Suspend-BitLocker\b"),
    re.compile(r"(?im)^\s*(?:&\s*)?Add-BitLockerKeyProtector\b"),
    re.compile(r"(?im)^\s*(?:&\s*)?Remove-BitLockerKeyProtector\b"),
    re.compile(r"(?im)^\s*(?:&\s*)?Restart-Computer\b"),
    re.compile(r"(?im)^\s*(?:&\s*)?manage-bde(?:\.exe)?\s+-(?:on|off)\b"),
]


def check_powershell_balance(text: str) -> str | None:
    stack: list[tuple[str, int]] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    opens = set(pairs.values())
    in_single = False
    in_double = False
    in_block_comment = False
    escaped = False
    index = 0
    line = 1
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if char == "\n":
            line += 1
        if in_block_comment:
            if char == "#" and next_char == ">":
                in_block_comment = False
                index += 2
                continue
            index += 1
            continue
        if not in_single and not in_double and char == "<" and next_char == "#":
            in_block_comment = True
            index += 2
            continue
        if not in_single and not in_double and char == "#":
            while index < len(text) and text[index] != "\n":
                index += 1
            continue
        if in_double:
            if escaped:
                escaped = False
            elif char == "`":
                escaped = True
            elif char == '"':
                in_double = False
            index += 1
            continue
        if in_single:
            if char == "'":
                if next_char == "'":
                    index += 2
                    continue
                in_single = False
            index += 1
            continue
        if char == '"':
            in_double = True
        elif char == "'":
            in_single = True
        elif char in opens:
            stack.append((char, line))
        elif char in pairs:
            if not stack or stack[-1][0] != pairs[char]:
                return f"unbalanced {char} at line {line}"
            stack.pop()
        index += 1
    if stack:
        return f"unclosed {stack[-1][0]} opened at line {stack[-1][1]}"
    if in_single or in_double or in_block_comment:
        return "unterminated string or block comment"
    return None


def main() -> int:
    errors: list[str] = []

    for path in sorted(ROOT.rglob("*.py")):
        if ".venv" in path.parts or "build" in path.parts or "dist" in path.parts:
            continue
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(f"Python compile failed: {path.relative_to(ROOT)}: {exc}")

    for path in sorted(ROOT.rglob("*.ps1")):
        if path in EXCLUDED:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        balance_error = check_powershell_balance(text)
        if balance_error:
            errors.append(f"PowerShell structural check failed: {path.relative_to(ROOT)}: {balance_error}")
        for pattern in FORBIDDEN_CALLS:
            match = pattern.search(text)
            if match:
                errors.append(
                    f"Forbidden executable operation in {path.relative_to(ROOT)} at offset {match.start()}: {match.group(0).strip()}"
                )

    required = [
        ROOT / "main.py",
        ROOT / "config.json",
        ROOT / "scripts" / "blade_operations.ps1",
        ROOT / "assets" / "bitlocker_assistant.ico",
        ROOT / "START_DEV.bat",
        ROOT / "BUILD_EXE.bat",
    ]
    for path in required:
        if not path.exists():
            errors.append(f"Required file missing: {path.relative_to(ROOT)}")

    operation_text = (ROOT / "scripts" / "blade_operations.ps1").read_text(encoding="utf-8", errors="replace")
    for operation in ("preflight", "fast_sync", "adaptive_sync", "policy_request", "gpupdate", "ccmcache_discovery", "sccm_log_evidence"):
        if f"'{operation}'" not in operation_text:
            errors.append(f"Required operation missing: {operation}")

    if errors:
        print("STATIC VALIDATION FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("STATIC VALIDATION PASSED")
    print("- Python source compiles")
    print("- Required project files exist")
    print("- PowerShell source passed structural delimiter/string balance checks")
    print("- No executable direct BitLocker modification or automatic reboot call found")
    print("- Dry-run SCCM log and ccmcache evidence operations are present")
    print("- Adaptive SCCM refresh operation is present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
