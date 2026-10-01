#!/usr/bin/env python3
"""SessionEnd hook: copy this session's transcript into docs/transcripts/.

Transcripts are required evidence (rubric H2). Saving them automatically means
you cannot forget — in MP1 nobody remembered. The name follows the required
pattern; set CMS_STUDENT=first-last in .env (or your shell) so it is right.

The copy is redacted as it is written (scripts/redact_transcripts.py):
passwords, secrets, tokens, and the author's email never reach the repo. If
redacting fails, it is copied as is, and .githooks/pre-commit refuses to
commit it until it is redacted.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


def student_slug(project: Path) -> str:
    name = os.environ.get("CMS_STUDENT")
    if not name:
        env = project / ".env"
        if env.exists():
            match = re.search(r"^CMS_STUDENT=(.+)$", env.read_text(), re.M)
            name = match.group(1).strip() if match else None
    return re.sub(r"[^a-z-]", "", (name or "your-name").lower().replace(" ", "-"))


def write_redacted(source: Path, target: Path, project: Path) -> None:
    script = project / "scripts" / "redact_transcripts.py"
    spec = importlib.util.spec_from_file_location("redact_transcripts", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    text, _ = module.redact_text(source.read_text(encoding="utf-8"))
    target.write_text(text, encoding="utf-8")


def main() -> None:
    event = json.load(sys.stdin)
    source = Path(event.get("transcript_path", ""))
    if not source.exists():
        return
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or ".")
    out = project / "docs" / "transcripts"
    out.mkdir(parents=True, exist_ok=True)
    number = f"{len(list(out.glob('*.md'))) + 1:02d}"
    target = out / (f"iphs400_mp2-cms_chat-session_{number}_"
                    f"{student_slug(project)}_{datetime.now().strftime('%Y%m%d')}.md")
    if not target.exists():
        try:
            write_redacted(source, target, project)
        except Exception:
            shutil.copy2(source, target)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
