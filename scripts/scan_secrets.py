"""Small repository secret scan for environments without gitleaks."""

from __future__ import annotations

import re

from scripts.benchmark_common import ROOT

EXCLUDED_PARTS = {
    ".env",
    ".git",
    ".mypy_cache",
    ".next",
    ".next-e2e",
    ".next-phase5-dev",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "node_modules",
    "playwright-report",
    "test-results",
}
TEXT_SUFFIXES = {
    ".css",
    ".env",
    ".example",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".lock",
    ".md",
    ".mjs",
    ".py",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "Groq API key": re.compile(r"\bgsk_[A-Za-z0-9]{20,}\b"),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "GitHub token": re.compile(r"\bgh[opsu]_[A-Za-z0-9]{30,}\b"),
    "nonempty AI API key": re.compile(r"(?m)^AI_API_KEY[ \t]*=[ \t]*([^\s#]+)"),
}
PLACEHOLDER_VALUES = {"changeme", "replace-me", "replace_me", "test", "your-key"}


def main() -> None:
    findings: list[str] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        if path.name != ".env.example" and path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            content = path.read_text(errors="strict")
        except (UnicodeDecodeError, OSError):
            continue
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(content):
                if label == "nonempty AI API key":
                    value = match.group(1).lower()
                    if value in PLACEHOLDER_VALUES or value.startswith(("<", "your-", "your_")):
                        continue
                line = content.count("\n", 0, match.start()) + 1
                findings.append(f"{path.relative_to(ROOT)}:{line}: {label}")

    if findings:
        print("Potential secrets found:")
        for finding in findings:
            print(f"- {finding}")
        raise SystemExit(1)
    print("Secret scan passed: no matching credentials or private keys found.")


if __name__ == "__main__":
    main()
