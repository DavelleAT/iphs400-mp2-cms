// What the Editor's modules share (static/editor.js and its editor-*.js):
// the body's fixed vocabulary, and small DOM helpers.

export const LINK = /^(https:\/\/|mailto:)/i;
// A link to a Report or Data Bite (app.site_links): stored by reference
// and resolved when the site is published.
export const SITE_LINK = /^(data-bite|report):[0-9a-f]{32}$/;
export const LOCKED = "[data-locked]";
export const CHART = "[data-chart]";
// What the body shows but doesn't edit in place.
export const SHOWN_ONLY = `${LOCKED}, ${CHART}`;
// The wrapper each table sits in (app.rendering), so a wide one scrolls.
export const TABLE_SCROLL = "content-table-scroll";
// The Editor's blocks, and the headings pasted ones become: the title is
// the page's only H1, and there is nothing below a Subsection.
export const HEADINGS = {H1: "h2", H2: "h2", H3: "h3", H4: "h3", H5: "h3", H6: "h3"};
export const BLOCKS = new Set(["P", "DIV", "LI", "UL", "OL", "BLOCKQUOTE", "TABLE", "THEAD",
                               "TBODY", "TFOOT", "TR", "TH", "TD", "SECTION", "ARTICLE",
                               "HEADER", "FOOTER", "PRE", ...Object.keys(HEADINGS)]);

// A table of `rows`, each a list of cells' contents: the first row the
// header, every row as wide as the widest, and an empty cell holding a
// line break so the cursor can go in it.
export function buildTable(rows) {
  const width = Math.max(1, ...rows.map((cells) => cells.length));
  const cell = (tag, content) => element(tag, {}, content.length ? content : [element("br")]);
  const row = (tag, cells) => element("tr", {}, Array.from({length: width},
                                                            (_, i) => cell(tag, cells[i] || [])));
  const [header = [], ...body] = rows;
  return element("table", {}, [element("thead", {}, [row("th", header)]),
                               element("tbody", {}, body.map((cells) => row("td", cells)))]);
}

export function tableWrapper(table) {
  return element("div", {class: TABLE_SCROLL}, [table]);
}

// Puts the cursor at the start of `node`.
export function caretIn(node) {
  const range = document.createRange();
  range.selectNodeContents(node);
  range.collapse(true);
  const selection = document.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
}

export function validUrl(href) {
  try {
    new URL(href);
    return true;
  } catch {
    return false;
  }
}

export function parseJson(text, fallback) {
  try {
    return text ? JSON.parse(text) : fallback;
  } catch {
    return fallback;
  }
}

export function hasFiles(transfer) {
  return Boolean(transfer) && [...transfer.types].includes("Files");
}

export function hidden(form, name) {
  const input = element("input", {type: "hidden", name});
  form.append(input);
  return input;
}

export function element(tag, attributes = {}, children = []) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value);
  node.append(...children);
  return node;
}

export function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}
