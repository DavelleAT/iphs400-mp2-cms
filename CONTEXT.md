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
An *uploaded* PNG, JPEG, or WebP picture (usually a chart made in Excel, R,
or Tableau) that a Data Bite or Report shows inline, placed in its body and
stored there as `image:<name>`. It belongs to its item and is published with
it (ADR-004). Not a **Chart**, which the CMS draws from data, and not a
Report's **attached file**, which is a PDF offered for download.
_Avoid_: figure, graphic, media, attachment

**Chart**:
A bar, horizontal bar, or line chart the CMS *draws* from data typed or
pasted into it, shown inline in a Data Bite or Report body with its data
available as a table (spec #14). Stored in the body as a `chart` block the
writer never sees. Not a **Chart image**, which is made elsewhere and uploaded.
_Avoid_: graph, plot, visualization

**Editor**:
The visual body editor on a Data Bite's or Report's edit page: a toolbar,
tables edited in place, Charts, and Chart images, with no Markdown in sight.
The body is still stored as Markdown (spec #14,
[ADR-005](docs/adr/ADR-005-editor-stores-markdown.md)). A part of a body it
can't represent is a **locked block**: shown read-only, kept byte for byte.
_Avoid_: WYSIWYG, rich text, rich-text editor

**Site link**:
A link in a Data Bite's or Report's body to another Data Bite or Report,
picked from a list in the Editor and stored by the target's immutable
reference (`report:<ref>`, `data-bite:<ref>`), never its title, slug, or id.
It is a link on the site only while its target is Published; otherwise it
shows as plain text (spec #14, T14).
_Avoid_: internal link, cross-reference

**Site preview**:
A Draft (or unsaved edits) rendered as its public page would look, with the
site's nav and stylesheet and a "Draft preview, not published" banner. Saves
nothing and publishes nothing.
_Avoid_: live view

**Confirmation**:
The one-line message the admin console shows, once, after a save, publish,
upload, delete, or user change succeeds (`app/flash.py`). Fixed text only:
never a title, email, filename, or password. A refused action gets an error,
not a Confirmation.
_Avoid_: flash, toast, notification, success message

**Factbook**:
A specific Report: the office's running reference document of admissions,
enrollment, diversity, and academic program statistics.

**Common Data Set (CDS)**:
A specific Report: a standardized annual institutional data submission,
published publicly.

**Survey Calendar**:
A specific Report: the schedule of past, current, and upcoming surveys the
office runs (e.g. faculty/staff surveys, external review surveys).
