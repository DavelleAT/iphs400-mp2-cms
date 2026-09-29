# Kenyon Office of Institutional Research (IR) CMS

A CMS for Kenyon College's Office of Institutional Research: a two-person office
(Director + Analyst/intern staff) that publishes survey results, data briefs,
and durable reference documents like the Factbook and Common Data Set.

## Language

**Director**:
The admin role. Modeled on the real office's Associate VP for Institutional
Research — the only person who can publish or edit a Report, manage user
accounts, and deactivate access.
_Avoid_: Admin, superuser

**Analyst**:
The editor role. Each intern gets their own named Analyst account (see
ADR-003). Can draft and publish Data Bites directly; can draft but not
publish or edit Reports. Any Analyst may edit any other Analyst's draft
(shift continuity), though the original author is preserved.
_Avoid_: Editor, intern (interns are Analysts, not a separate role), staff

**Data Bite**:
A Post: a short, dated item — a survey result, an enrollment snapshot, an
announcement. The frequent, low-stakes content type. Analysts can publish
these without Director approval.
_Avoid_: Update, post, announcement, article

**Report**:
A Page: a durable, cite-able reference document — the Factbook, a Common Data
Set, the Survey Coordination Policy. Appears in public navigation. Only the
Director can publish or edit a Report, even one an Analyst drafted.
_Avoid_: Page, document

**Draft**:
Content (a Data Bite or Report) that has been saved but not published. Never
appears on the public site. Used for unreleased data, e.g. enrollment numbers
still being verified before the official count.
_Avoid_: Unpublished, pending

**Published**:
Content visible on the public site. The one-way gate: a Report only crosses
it with Director action.
_Avoid_: Live, public

**Chart image**:
A PNG, JPEG, or WebP picture (usually a graph made in Excel, R, or Tableau)
that a Data Bite or Report shows inline, placed in its Markdown body as
`image:<name>`. It belongs to its item and is published with it (ADR-004).
Not a Report's **attached file**, which is a PDF offered for download.
_Avoid_: figure, graphic, media, attachment

**Factbook**:
A specific Report: the office's running reference document of admissions,
enrollment, diversity, and academic program statistics.

**Common Data Set (CDS)**:
A specific Report: a standardized annual institutional data submission,
published publicly.

**Survey Calendar**:
A specific Report: the schedule of past, current, and upcoming surveys the
office runs (e.g. faculty/staff surveys, external review surveys).
