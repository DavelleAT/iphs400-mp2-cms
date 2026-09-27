#!/usr/bin/env python3
"""Check your submission before you send it. The judge runs this first.

    uv run python scripts/check_submission.py --stage 1
    uv run python scripts/check_submission.py --stage 2
    uv run python scripts/check_submission.py --stage 2 --json

Stage 0 is the instructor's check of the template itself.
Exit code 0 means every check passed.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET = re.compile(r"(sk-[A-Za-z0-9]{16,}|ANTHROPIC_AUTH_TOKEN\s*[:=]\s*\S{8,}|-----BEGIN [A-Z ]*PRIVATE KEY)")
REPORT = re.compile(r"^iphs400_mp2-web-cms_report_[a-z]+-[a-z-]+_\d{8}\.md$")
TRANSCRIPT = re.compile(r"^iphs400_mp2-cms_chat-session_\d{2}_[a-z]+-[a-z-]+_\d{8}\.md$")
SCREENS = ["login", "dashboard", "content-list", "editor", "users", "editor-denied"]


def sh(*args: str) -> str:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True).stdout


class Checks:
    def __init__(self) -> None:
        self.results: list[dict] = []

    def add(self, ok: bool, name: str, detail: str, fix: str = "") -> None:
        self.results.append({"check": name, "ok": bool(ok), "detail": detail, "fix": fix})

    # --- checks -----------------------------------------------------------
    def hygiene(self) -> None:
        tracked = sh("git", "ls-files").splitlines()
        bad = [f for f in tracked if f.endswith((".db", ".env")) or f.startswith(".claude/state/")]
        self.add(not bad, "no database or .env committed", ", ".join(bad) or "clean",
                 "git rm --cached <file>, confirm .gitignore covers it, then rewrite history if it is old")
        history = sh("git", "log", "--all", "-p", "--", ".")
        hits = sorted(set(SECRET.findall(history)))
        self.add(not hits, "no secrets in history", f"{len(hits)} match(es)",
                 "rotate the key first, then ask Claude to rewrite history")
        self.add((ROOT / ".env.example").exists(), ".env.example present", "", "restore it from the template")

    def docs(self, stage: int) -> None:
        pairs = [
            ("notes/cms-field-notes.md", "field notes"),
            ("CONTEXT.md", "glossary"),
            ("notes/token-budget-plan.md", "token budget plan"),
            ("notes/usage-ledger.csv", "usage ledger"),
            ("docs/process/compaction-log.md", "compaction log"),
        ]
        if stage >= 2:
            pairs += [("README.md", "README"), ("scripts/seed_demo.py", "seed script")]
        for path, label in pairs:
            self.add((ROOT / path).exists(), f"{label} present", path, f"create {path}")
        if stage >= 2:
            handoffs = list((ROOT / "docs" / "handoff").glob("*.md"))
            self.add(bool(handoffs), "at least one handoff saved", f"{len(handoffs)} file(s)",
                     "copy a /handoff document into docs/handoff/")

    def naming(self, stage: int) -> None:
        reports = list((ROOT / "docs").glob("iphs400_mp2-web-cms_report_*.md"))
        if stage >= 2:
            ok = any(REPORT.match(p.name) for p in reports)
            self.add(ok, "report named correctly",
                     ", ".join(p.name for p in reports) or "missing",
                     "iphs400_mp2-web-cms_report_{first}-{last}_{YYYYMMDD}.md, lowercase")
        transcripts = list((ROOT / "docs" / "transcripts").glob("*.md"))
        bad = [p.name for p in transcripts if not TRANSCRIPT.match(p.name)]
        self.add(transcripts and not bad, "transcripts present and named correctly",
                 f"{len(transcripts)} file(s); bad: {bad or 'none'}",
                 "iphs400_mp2-cms_chat-session_{NN}_{first}-{last}_{YYYYMMDD}.md")

    def readme(self, stage: int) -> None:
        if stage < 2:
            return
        text = (ROOT / "README.md").read_text() if (ROOT / "README.md").exists() else ""
        for needle, label in [("http", "live URL"), ("Run locally", "run-locally section"),
                              ("Generative AI Use Statement", "AI Use Statement")]:
            self.add(needle.lower() in text.lower(), f"README has {label}", "",
                     f"add the {label} to README.md")
        placeholder = "*(Required. Replace this section" in text
        self.add(not placeholder, "AI Use Statement was rewritten", "",
                 "replace the template placeholder with your own statement")

    def screenshots(self, stage: int) -> None:
        if stage < 2:
            return
        files = {p.name.lower() for p in (ROOT / "docs" / "screenshots").glob("*")}
        missing = [f"{s}-{w}" for s in SCREENS for w in (1280, 390)
                   if not any(s in n and str(w) in n for n in files)]
        self.add(not missing, "12 screenshots present", ", ".join(missing) or "all present",
                 "docs/screenshots/{screen}-{1280|390}.png for each of: " + ", ".join(SCREENS))

    def git_state(self, stage: int) -> None:
        tags = sh("git", "tag").split()
        want = ["mp2-mvp"] + (["mp2-final"] if stage >= 2 else [])
        for tag in want:
            self.add(tag in tags, f"tag {tag} exists", ", ".join(tags) or "none",
                     f"git tag {tag} && git push --tags")
        paths = sh("git", "grep", "-l", '-e', 'href="/', "-e", 'src="/', "--", "*.html")
        self.add(not paths.strip(), "no root-absolute paths in HTML", paths.strip() or "clean",
                 'use relative paths ("style.css"), not "/style.css"')

    def tests(self) -> None:
        run = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT,
                             capture_output=True, text=True)
        self.add(run.returncode == 0, "test suite passes",
                 run.stdout.strip().splitlines()[-1] if run.stdout else "",
                 "fix failing tests before submitting")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", type=int, choices=[0, 1, 2], default=2)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    c = Checks()
    c.hygiene()
    if args.stage == 0:
        for path in ["app/main.py", "scripts/seed_demo.py", ".claude/settings.json",
                     "CLAUDE.md", "SECURITY-CHECKLIST.md"]:
            c.add((ROOT / path).exists(), f"template file {path}", "", "restore from the dev repo")
    else:
        c.docs(args.stage)
        c.naming(args.stage)
        c.readme(args.stage)
        c.screenshots(args.stage)
        c.git_state(args.stage)
        c.tests()

    failures = [r for r in c.results if not r["ok"]]
    if args.json:
        print(json.dumps({"stage": args.stage, "failures": len(failures),
                          "results": c.results}, indent=2))
    else:
        for r in c.results:
            print(f"{'PASS' if r['ok'] else 'FAIL'}  {r['check']}"
                  + (f"  [{r['detail']}]" if r["detail"] else ""))
            if not r["ok"] and r["fix"]:
                print(f"      fix: {r['fix']}")
        print(f"\n{len(c.results) - len(failures)}/{len(c.results)} checks passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
