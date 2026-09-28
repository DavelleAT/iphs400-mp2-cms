# Analysts publish Data Bites directly; only the Director publishes Reports; each intern gets their own Analyst account

**Status:** accepted (supersedes an earlier draft of this ADR that proposed one shared Analyst account)

Analysts (interns) currently email IR staff or drop files in a shared
OneDrive folder to get anything posted, which is the exact bottleneck this
CMS exists to remove. But Reports (Factbook, Common Data Set, Survey Policy)
get cited externally and must stay accurate and stable, so we don't want
intern turnover or a drafting mistake taking one live unreviewed.

We decided: the editor permission is split by content type, not uniform.
Analysts can create, edit, and **publish** a Data Bite without approval.
Analysts can create and edit a Report, but only the Director (admin) can
publish or edit a Report once it exists — even one an Analyst drafted.

**Accounts:** each intern gets their own named Analyst account, not a shared
login. This reverses an earlier version of this decision. Trying WordPress
Playground surfaced the reason: a shared account makes every Data Bite's
author say "Analyst," with no way to tell which intern actually wrote it,
which felt wrong the moment it was compared against a real WordPress content
list showing a real name. Individual accounts cost the Director a few extra
minutes of user management per intern rotation (create/deactivate each
semester) — worth it for honest attribution.

**Shift continuity is preserved despite individual accounts:** any Analyst
may edit any other Analyst's draft (Data Bite or draft Report), so a
half-finished item from last week's intern doesn't need Director
intervention to pick back up. Editing preserves the original author and
`created_at`; only `updated_at` changes. This means "Analyst" is a role, not
an ownership boundary — the boundary that matters is Analyst vs. Director,
not Analyst-A vs. Analyst-B.

The alternative (uniform editor rights, or a Director-approves-everything
gate) was rejected: the former risks an intern accidentally publishing a
Factbook revision, the latter reintroduces the "email IR to post something"
bottleneck for the routine, low-stakes case.
