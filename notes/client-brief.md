# Client brief — Kenyon Office of Institutional Research

**Who runs it, how comfortable are they with computers?** Two people: a
Director (modeled on the real office's Associate VP for IR) and
Analysts/interns who rotate by semester. Comfortable with spreadsheets and
Word, not with anything more technical — Markdown with a preview is about the
ceiling.

**Who reads it, what are they after?** Split audience. Internally, faculty
and administrators come back for the current Factbook and enrollment numbers.
Accreditors and board members want historical reports for self-studies.
Externally, some of it — the Factbook, Common Data Set, Data Gallery — is
genuinely public, matching what's actually live on kenyon.edu today.

**What's broken now?** Reports live scattered across a shared OneDrive
folder with inconsistent naming. Multiple interns work on things at the same
time, so it's unclear which version is current, and people end up emailing
IR directly to ask "what's the latest Factbook" instead of finding it
themselves.

**What would make them say "this is better"?** Whichever intern is on shift
can draft and publish a routine Data Bite, under their own Analyst account,
without emailing a link around or waiting on the Director — and can pick up
a draft another intern started without needing anyone's help. The Director
can see everything — drafts and published — in one dashboard before anything
sensitive goes live. And once something's published, people stop emailing IR
to ask where the latest Factbook is.

**What must never happen?** Draft or unreleased data (e.g. this term's
still-being-verified enrollment numbers) must never appear on the public
site before it's official. Relatedly, a Report that's already published and
cited elsewhere (Factbook, CDS) must never be editable or publishable by
anyone but the Director — see [ADR-003](../docs/adr/ADR-003-split-publish-rights.md).
Each intern has their own Analyst account, so authorship on a Data Bite is
always honest — this was a change from an earlier shared-account plan, made
after trying WordPress Playground and seeing how much better a real name
looked in the content list.
