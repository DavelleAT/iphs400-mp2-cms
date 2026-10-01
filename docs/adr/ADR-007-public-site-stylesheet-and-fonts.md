# ADR-007: The public site's own stylesheet, self-hosted fonts, and 404.html

**Status:** accepted (spec #22, ticket #23)
**Date:** 2026-10-01

## Context

Before spec #22, the public site and the admin console shared one stylesheet:
a Python string, `app.public_site.CSS`, served at `style.css` and written
there by `cms publish`. The public site's rules and every `.admin-*` rule
were in it, so each side's styles reached the other's pages. Spec #22 gives
the public site a real design ("set like a dataset") with its own typefaces,
and leaves the console's look as it is until a later spec.

The site is served from a GitHub Pages subfolder with relative paths only
(ADR-001), and `pyproject.toml` is fixed (ADR-002).

## Decision

- **Two stylesheets, as files.** `static/site.css` is the public site's. The
  app serves it at `style.css`, the Site preview serves it from its own copy
  of the site, and `cms publish` copies it to `site/style.css`. All three read
  the file through `app.public_site.assets()`. `static/admin.css` is the
  console's: the old rules unchanged, minus the Site preview banner, served at
  `/admin.css` (outside the login, so the login page has it). It is never
  exported. `public/layout.html` is a standalone layout and `base.html` stays
  the console's, so neither links the other's stylesheet. Tests check both
  directions.
- **Self-hosted fonts.** Atkinson Hyperlegible Next (roman and italic) and
  Atkinson Hyperlegible Mono, as variable `.woff2` files in `static/fonts/`.
  Each font's SIL Open Font License is committed beside it. They are served
  and exported at `fonts/` beside the stylesheet, which loads them by relative
  `url()`s, together with the licences. The footer links the licences, so they
  travel with the fonts and the crawler reaches them. There is no CDN: a font
  host would be a second origin and a request for every visitor.
- **404.html carries a `<base>`.** GitHub Pages serves `404.html` at whatever
  missing URL was asked for, at any depth, so a relative link in it resolves
  against the wrong folder. With `CMS_BASE_PATH` set to the deployed site's
  full URL (given a trailing `/` if it lacks one), `404.html` has
  `<base href="CMS_BASE_PATH">`, and its links work at any depth. A value
  that isn't an `http(s)://` URL is ignored, since a path alone would be a
  root-absolute link. With it
  unset (local use), it inlines its stylesheet and links as from the site's
  root, which is right for a miss at the top level. Fonts then load only for
  a top-level miss.
- **The crawler's one exception.** The T07/T08 crawler, which fails on any
  root-absolute or absolute site link, allows exactly one `<base>`, in
  `404.html`. The crawler starts from `index.html` and `404.html`, and follows
  the stylesheet's `url()`s.
- **The skip link under a `<base>`.** `#main` resolves against a `<base>`,
  not the page. `404.html`'s `<base>` is the site's root, so its skip link is
  `404.html#main`: the same page, at its own path. A Site preview, a
  sandboxed frame in the console, has no skip link.
- **Chart series, by count, the newest last.** One series is Kenyon purple;
  two are bright purple then Kenyon purple, as spec #22 says. A third and
  fourth series are greys (`#8A849B`, then `#5D5870` in light and `#E4E0EE`
  in dark), not more bright purple, so no two series share a colour. Citron
  stays off Charts: it is the field's accent only. In dark mode, Kenyon
  purple `#4B2E84` is 1.8:1 on the dark paper, so the newest series takes
  the dark theme's Kenyon purple step, the light `#A99CFF`, and bright purple
  a deeper `#6352D6` (3.4:1) to stay apart from it. The colours come from
  `:has()` on the figure; without it every series is Kenyon purple.

## Consequences

- A designer can change the public site's CSS without touching Python, and
  without risk to the console's styles.
- The console still looks like it did before spec #22. Its own redesign is a
  later spec, and it will start from `static/admin.css`.
- A font update is a file swap. The licence files have to be kept with the
  fonts.
## Why this is an ADR

It changes how every page gets its styles and where the site's files come
from, and the `<base>` in `404.html` is the one exception to ADR-001's
relative-links rule. That is surprising without the reason.
