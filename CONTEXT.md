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

**State**:
Whether a Data Bite or Report is a Draft or Published. The Console's lists
show it as a badge and filter by it (spec #25, T22). In code and in the
lists' `?status=`, it is `status`.
_Avoid_: status (on a page), stage

**Chart image**:
An *uploaded* PNG, JPEG, or WebP picture (usually a chart made in Excel, R,
or Tableau) that a Data Bite or Report shows inline, placed in its body with
the Editor's "Insert image", with a required description, and stored there as
`image:<name>` (T18). It belongs to its item and is published with
it (ADR-004). Not a **Chart**, which the CMS draws from data, and not a
Report's **attached file**, which is a PDF offered for download.
_Avoid_: figure, graphic, media, attachment

**Chart**:
A bar, horizontal bar, or line chart the CMS *draws* from data typed or
pasted into it, shown inline in a Data Bite or Report body with its data
available as a table (spec #14,
[ADR-006](docs/adr/ADR-006-charts-drawn-from-data.md)). Stored in the body
as a `chart` block the writer never sees. Not a **Chart image**, which is made elsewhere and uploaded.
_Avoid_: graph, plot, visualization

**Chart builder**:
The Editor's "Insert chart" dialog: a Chart's fields and a grid (categories
down, series across) that takes typing or a paste from Excel or Sheets, with
the Chart drawn by the server as the writer types and each error beside its
field or cell (spec #14, T17). In the body, a Chart shows as a *card*, its
drawing with Edit and Remove.
_Avoid_: chart editor, chart wizard

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
reference, its *site reference* (`report:<ref>`, `data-bite:<ref>`), never
its title, slug, or id.
It is a link on the site only while its target is Published; otherwise it
shows as plain text (spec #14, T14).
_Avoid_: internal link, cross-reference

**Address**:
Where a Data Bite's or Report's page is on the site: its type's folder, its
slug, and `.html` (e.g. `data-bites/fall-enrollment.html`). The edit page
shows the slug as an Address field, the folder and `.html` either side of it
(spec #25, T23). In code, and in the form, the part typed is the `slug`.
_Avoid_: URL, permalink, slug (on a page)

**Site preview**:
A Draft (or unsaved edits) rendered as its public page would look, with the
site's nav and stylesheet and a "Draft preview, not published" banner. Saves
nothing and publishes nothing.
_Avoid_: live view

**Summary**:
One or two sentences of plain text about a Data Bite or Report, at most 200
characters, written under its title on the edit form. Shown under the title
on its page, in the lists and the Reports table, and in its page's
description and link-preview tags (spec #22, T20). Optional: an item without
one shows nothing in its place.
_Avoid_: excerpt, abstract, description, blurb

**Homepage settings**:
The homepage's headline, its accent (the end of the headline, in bright
purple), its intro, and its Key figures. Edited by the Director only, at
/admin/homepage. Settings, not content: no Draft, and on the public site from
the next `cms publish`, like a change to the nav (spec #22, T20).
_Avoid_: hero, homepage content

**Key figure**:
One of up to four numbers on the homepage, each a value, a label saying what
it counts, and an optional note saying when or of whom (e.g. "1,805" /
"Students enrolled" / "Fall 2026 census"). Typed text, not drawn from data.
_Avoid_: stat, KPI, metric

**Site search**:
The public site's search of published titles and Summaries, entirely static:
`cms publish` writes `search-index.json` and `search.html`, and
`search.js` searches the index in the browser. Without JavaScript,
`search.html` lists every published item. Bodies are not searched (spec #22,
T20).
_Avoid_: search engine, full-text search

**Confirmation**:
The one-line message the admin console shows, once, after a save, publish,
upload, delete, or user change succeeds (`app/flash.py`). Fixed text only:
never a title, email, filename, or password. A refused action gets an error,
not a Confirmation.
_Avoid_: flash, toast, notification, success message

**Console**:
The admin console: the local, signed-in app where the Director and Analysts
write and publish content, never on the public internet. Every page has the
same bar: numbered nav (01 Dashboard, 02 Data Bites, 03 Reports, and, for
the Director, 04 Homepage and 05 Users), who is signed in, "View site ↗",
and Log out (spec #25, T21). Its home page is the **Dashboard**.
_Avoid_: back end, dashboard (that is its home page only)

**Dashboard**:
The Console's home page: counts of each type by State, then "Waiting for
you" and "Recently changed" (spec #25, T24). What is waiting is derived from
what is stored, with no review step: for the Director, every Draft Report
(only they can publish one); for an Analyst, their own Drafts.
_Avoid_: home, overview, inbox

**Factbook**:
A specific Report: the office's running reference document of admissions,
enrollment, diversity, and academic program statistics.

**Common Data Set (CDS)**:
A specific Report: a standardized annual institutional data submission,
published publicly.

**Survey Calendar**:
A specific Report: the schedule of past, current, and upcoming surveys the
office runs (e.g. faculty/staff surveys, external review surveys).
