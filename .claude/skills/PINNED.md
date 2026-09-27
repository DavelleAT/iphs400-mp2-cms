# Pinned skills

Install the mattpocock engineering skills into this repo, then configure them
once. Everyone in the class uses the same version, so the manual's commands match
what you see.

```bash
npx skills@latest add mattpocock/skills
claude
# then, inside Claude Code:
/setup-matt-pocock-skills      # tracker: GitHub · labels: defaults · docs: single context
```

The flow you will use: `/grill-with-docs → /to-spec → /to-tickets → /implement → /code-review`.
Help commands: `/ask-matt` (which skill fits), `/wait-what` (that did not land),
`/teach` (learn a topic across sessions).

**Name clash:** this set ships its own `/teach`, which is not the `/teach` you
wrote in Week 4. If you want yours here, copy it to
`.claude/skills/teach-log/SKILL.md` and rename it inside the file.

**Record the version you installed** in `notes/setup_check.md`:

```bash
claude --version >> notes/setup_check.md
ls .claude/skills >> notes/setup_check.md
```
