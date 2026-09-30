# ADR-001: The admin console runs locally; the public site is a static export

**Status:** accepted (set by the assignment)
**Date:** 2026-09-22

## Context

A CMS needs a server, a database, and login. GitHub Pages serves static files
only: it cannot run Python and has no database. Students have two weeks and no
hosting budget, and a first web application with real authentication is an
attractive target the moment it is public.

## Decision

The admin console (FastAPI + SQLite) runs on the student's own machine. A
`cms publish` step renders the published content to static HTML in `site/`, which
is deployed to GitHub Pages on the `gh-pages` branch.

## Consequences

- Login, roles, and the database are never exposed to the internet.
- The public site cannot have server-side features (search, comments) without a
  different host; a stretch goal may add a live admin deploy behind a security gate.
- Publishing is explicit: content changes are not live until `cms publish` runs,
  which is a behaviour worth documenting for your client.
- Relative paths become mandatory, because Pages serves the site from a subfolder.

**Note (2026-09-30, T14, spec #14):** the rule is restated as "every
*site-owned* link and asset uses a relative path". An explicit external link
(an `<a href>`) may be absolute, but only as `https:` or `mailto:`. A link to
another Report or Data Bite is stored as `report:<ref>` or `data-bite:<ref>`
and resolved to a page-relative path when the site is rendered, so it
survives slug changes and the site moving. The render pipeline enforces this
for every body (anything else renders as its link text), and the T07/T08
crawler skips only `https:`/`mailto:` `<a href>`s.

## Why this is an ADR

It is hard to reverse (it shapes every route, template, and deploy step) and it
is surprising without context (most CMSes are servers). That is the bar; most
decisions do not meet it and belong in the spec or the glossary instead.
