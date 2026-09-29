# Data Bites and Reports carry chart images, referenced from the Markdown body

**Status:** accepted (reverses the original spec's "uploads for Data Bites" exclusion, #1; spec #11)

The office's content is mostly numbers, and it already makes charts of them
in Excel, R, and Tableau. The original spec kept Data Bites Markdown-only and
gave Reports one attached PDF, so a chart had nowhere to go except an image
link to some other host. That puts it outside the draft/publish gate, and it
breaks when the other host changes.

We decided: **both** Data Bites and Reports can carry chart images, uploaded on
the item's edit page and placed in its Markdown body as `image:<name>`.
Data Bites were included on purpose, not only Reports. A Data Bite such as
"Fall enrollment snapshot" is exactly where a chart is wanted.

**Uploaded files, not generated charts.** The CMS stores and shows a chart
someone made elsewhere; it does not draw one from data. That keeps the stack
unchanged (no charting or image library, `pyproject.toml` is fixed), works
with whatever tool the office already uses, and leaves no JavaScript on the
public site. Charts drawn from a data block in the Markdown were considered
and deferred as a possible stretch. Embeds (Tableau Public, Power BI) were
rejected, because they need `<iframe>` through the sanitizer.

**Raster only: PNG, JPEG, WebP. No SVG.** An SVG is a document that can carry
`<script>` and event handlers, and serving an uploaded one from the site's own
origin would reopen the hole the Markdown sanitizer closes. Content is checked
by signature, the way T05 checks a PDF, because there is no decoding library.

**`image:<name>`, resolved at render time.** The body never holds a path. The
Markdown pipeline turns `image:<name>` into the URL for the page being rendered
(admin preview, public page, or export), so one stored body works at every
depth and the published HTML stays relative. An unknown name renders nothing.

**An image belongs to its item.** It is public only while that item is
published, and it follows that item's permissions (ADR-003 unchanged): any
Analyst may manage a Data Bite's images or a draft Report's, and only the
Director a published Report's. Deleting the item deletes its images.
