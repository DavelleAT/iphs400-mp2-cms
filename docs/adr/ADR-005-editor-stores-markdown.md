# ADR-005: The Editor stores Markdown

**Status:** accepted (spec #14, ticket #16)
**Date:** 2026-09-30

## Context

The office's writers are IR staff and interns, not web developers, and every
body was typed as Markdown in a textarea. Spec #14 replaces the textarea with
the **Editor**, a visual editor. That raises two questions: what the body is
stored as, and what the Editor is built with.

Storing the Editor's HTML was considered and rejected. Every body already
stored, the sanitizer, `cms publish`, and every test assume Markdown; HTML
from a browser's `contenteditable` differs by browser and would change
whenever the same body is opened and saved; and the site would have to trust
stored HTML rather than render it. A Markdown or visual editor library was
rejected too: `pyproject.toml` is fixed, and ADR-002 has no build step.

## Decision

**The body stays Markdown.** The Editor is `contenteditable` and a toolbar in
plain JavaScript (`static/editor.js`), with no dependency.

- On load, the server renders the body to the Editor's HTML with the site's
  own pipeline (`app.editor`). On save, the Editor posts its HTML, and the
  server sanitizes it with nh3 and turns it into Markdown with stdlib
  `html.parser` (`app.markdown_form`), always in one **standard form**.
- **Untouched is byte-for-byte.** The Editor posts `body_dirty=0` until the
  writer's first change, and then the server keeps the stored body and ignores
  the posted HTML. The client can only choose "keep what is stored", so the
  flag grants nothing. Opening and saving an item never rewrites its body.
- **The base version.** The edit form carries `item_base`, a SHA-256 of the
  stored title, slug, and body. A save from a form opened on an older version
  is refused whole ("This item changed since you opened it."), checked again in
  the same transaction as the write. Nothing is merged.
- **Locked blocks.** A top-level block the Editor can't represent (a code
  block, raw HTML, an H1 or H4, a rule, an inline code span, a link that isn't
  `https:`, `mailto:`, or a site link (`report:<ref>`, `data-bite:<ref>`, added
  by T14), ...) is cut out and replaced by a `locked-<n>` token.
  The Editor shows its rendered, sanitized HTML, read-only, with a Remove
  button; its Markdown never reaches the browser. On save each token is
  replaced by that block's bytes from the **stored** body, never from the post.
  An unknown, repeated, or filled-in token refuses the save; a missing one was
  removed.
- **The fallback.** If the script doesn't run, the textarea still posts
  Markdown: the body with each locked block as its token line, restored the
  same way on save.

## Consequences

- The sanitizer, `cms publish`, the public site, and all stored content are
  unchanged. A body can still be written as Markdown through the fallback.
- A body the Editor has changed is rewritten in the standard form: the same
  rendered HTML, but not the writer's original spacing or list markers. Only
  a changed body is rewritten.
- The Editor can only offer what Markdown can hold: no underline, fonts,
  colours, or alignment.
- Content the Editor can't represent stays safe but read-only in it, until
  someone removes it or edits it through the fallback.
- A link reference definition (`[x]: https://...`) is not a block, so it is
  not kept when the Editor rewrites a body; a link that used it is written
  inline instead. A locked block that used one loses its link.
- `app.markdown_form` is the one place that decides what the standard form is.
  T15 (tables) and T16 (Charts) extend it rather than adding their own.
