# ADR-006: Charts drawn from data

**Status:** accepted (spec #14, ticket #19). Reverses ADR-004's deferral of
charts drawn from a data block.
**Date:** 2026-10-01

## Context

ADR-004 gave Data Bites and Reports uploaded **Chart images** and deferred
charts the CMS draws itself. Making a chart still means Excel, an export, an
upload, and `image:<name>`. Spec #14 asks for a **Chart** built from data typed
or pasted into the CMS, so a survey result gets a chart without leaving it.

There's no charting library (`pyproject.toml` is fixed), and the public site
has no JavaScript. Whatever draws the chart has to be server-side Python, and
it has to put SVG into pages *after* nh3, which would strip it otherwise.

## Decision

**A Chart is a `chart` fence in the body, holding one strict JSON object,
drawn by the server as inline SVG.** The body is still Markdown (ADR-005).
`app.charts` owns the grammar (version 1, spec #14's table) and the number,
unit, missing, and suppressed rules. `app.chart_drawing` draws a Chart that
has passed them, and `app.rendering` puts it in the page.

- **Strict, and checked on every save.** The JSON is parsed by stdlib `json`
  with duplicate keys, `NaN`, and `Infinity` refused. Unknown keys, wrong
  types, over-long or multi-line strings, and blocks over 32 KB are refused.
  A cell that isn't a number is refused unless it's a missing or suppressed
  value. A body with an invalid Chart isn't saved, from the Editor or the
  Markdown fallback (`app.content.validate`), and the error names the Chart
  and the problem.
- **Values are kept as typed.** A cell is stored as the writer typed it
  (`"1,200"`, `"<10"`, `"n/a"`) and parsed when drawn, so labels and the
  "Show the data" table show the original notation and suppressed values
  survive.
- **One unit per Chart.** `$` is a prefix, and `%` or a word is a suffix. A
  Chart with no stated unit takes the first one in its data, which isn't
  written back into the block. A cell in another unit, or any other
  currency, is refused.
- **Canonical form, only when edited.** A Chart saved from an edited body is
  rewritten in one form: keys in the grammar's order, absent optional keys
  left out, `json.dumps(..., ensure_ascii=False, indent=2)`, NFC strings. An
  untouched body, or a Chart the Editor shows as a locked block, keeps its
  bytes (ADR-005).
- **The trusted SVG boundary.** Nothing inserted after nh3 is sanitized
  again, so a Chart is safe because of how it's built, not by filtering:
  - Each render takes a fresh `secrets.token_hex(16)` nonce *after* the body
    is fixed. Each valid Chart becomes the placeholder `chart-<nonce>-<n>`
    before nh3. After nh3, each placeholder must be there exactly once, or
    the render raises rather than emit anything partial. A writer can't type
    a placeholder that matches, because the nonce doesn't exist yet.
  - Only a Chart that passed the full grammar is drawn, and every value
    must pass `math.isfinite`.
  - The drawing emits a fixed set of elements and attributes. Numbers are
    formatted by the renderer, `fill` and `stroke` come only from the
    palette, and `class` only from fixed names. There's never an `href`,
    `style`, or `on*` attribute. Every writer string is escaped *text
    content* only.
  - An invalid Chart that reaches rendering anyway (stored under older
    rules) shows "This chart could not be shown." and nothing from the block.
- **The accessible name's id is deterministic.** Each Chart's SVG is named
  by its title through `aria-labelledby`, pointing at the id
  `chart-<key>-<n>-title`. `<key>` is 32 hex characters from a hash of the
  body, not the per-render nonce. So the export stays byte-for-byte the live
  site, and a publish doesn't change every page that has a Chart. The nonce
  stays secret and only ever marks placeholders.
- **A fixed palette.** Four series colours, the first four slots of the
  dataviz reference palette, with their dark-mode steps swapped in by class.
  Both sets pass its validator (colour-blind separation, normal-vision
  separation, lightness band). In light mode, aqua and yellow are under 3:1
  against white, so every Chart carries a legend for two or more series and
  its data table.
- **Drawn twice, for the column and for a phone.** An SVG scales its text
  with it, so one drawing wide enough for the desktop column puts its text
  near 9 px on a phone. Each Chart is drawn 520 and 360 units wide, and the
  stylesheet shows the narrow one below 30rem (`display: none` takes the
  other out of the accessibility tree). Both name the same title.
- **No JavaScript on the public site.** The data table is a `<details>`
  element. Bar charts start at zero. A line chart may start above zero, and
  says so.

## Consequences

- Uploaded Chart images stay (ADR-004), and no uploaded SVG is ever served.
- The Editor shows a Chart as a locked block, drawn and read-only, until
  the Chart builder (T17) gives it an editable card.
- A future grammar version needs a new `version` and must keep reading
  version 1, because stored bodies are never rewritten unless edited.
- Pie, stacked, scatter, and dual-axis charts, and colour choice, are out of
  scope (spec #14).
