// Cleaning a paste (static/editor.js): only what the Editor supports
// survives, and a range copied from a spreadsheet becomes a table.

import {BLOCKS, HEADINGS, LINK, SITE_LINK, buildTable, element, escapeHtml, tableWrapper,
        validUrl} from "./editor-dom.js";

const SKIPPED = new Set(["SCRIPT", "STYLE", "TEMPLATE", "HEAD", "TITLE", "META", "LINK",
                         "IFRAME", "OBJECT", "EMBED", "SVG", "MATH", "NOSCRIPT", "BUTTON",
                         "INPUT", "SELECT", "TEXTAREA"]);

// The cleaned paste, as the children of a <div>.
export function cleanPasted(html) {
  // DOMParser's document is inert: no script runs and nothing loads.
  const source = new DOMParser().parseFromString(html, "text/html");
  wordLists(source.body);
  regularTables(source.body);
  const state = {droppedPicture: false};
  const out = document.createElement("div");
  for (const node of [...source.body.childNodes]) out.append(...clean(node, state));
  return {html: out, droppedPicture: state.droppedPicture};
}

// Nodes as blocks: each run of inline nodes between blocks a paragraph.
export function asBlocks(nodes) {
  const blocks = [];
  let run = null;
  for (const node of nodes) {
    if (node.nodeType === Node.ELEMENT_NODE && BLOCKS.has(node.tagName)) {
      blocks.push(node);
      run = null;
    } else if (node.nodeType === Node.ELEMENT_NODE || node.data.trim()) {
      if (!run) blocks.push(run = element("p"));
      run.append(node);
    }
  }
  return blocks;
}

function clean(node, state) {
  if (node.nodeType === Node.TEXT_NODE) return [document.createTextNode(node.data)];
  if (node.nodeType !== Node.ELEMENT_NODE) return [];
  const tag = node.tagName.toUpperCase();
  if (SKIPPED.has(tag)) return [];
  if (tag === "IMG" || tag === "PICTURE" || tag === "VIDEO" || tag === "CANVAS") {
    state.droppedPicture = true;
    return [];
  }
  const inner = () => [...node.childNodes].flatMap((child) => clean(child, state));
  const style = node.getAttribute("style") || "";
  if (tag === "BR") return [element("br")];
  if (tag in HEADINGS) return [element(HEADINGS[tag], {}, inner())];
  if (tag === "TABLE") return [tableWrapper(element("table", {}, inner()))];
  if (["P", "UL", "OL", "BLOCKQUOTE", "THEAD", "TBODY", "TFOOT", "TR", "TH", "TD"]
      .includes(tag)) {
    const attributes = tag === "OL" && node.getAttribute("start") ? {start: node.getAttribute("start")} : {};
    return [element(tag.toLowerCase(), attributes, inner())];
  }
  if (tag === "LI") {
    // A list item holding one paragraph (as Google Docs pastes) is that
    // paragraph's text.
    const children = inner();
    const only = children.filter((child) => child.nodeType === Node.ELEMENT_NODE || child.data.trim());
    const content = only.length === 1 && only[0].tagName === "P" ? [...only[0].childNodes] : children;
    return [element("li", {}, content)];
  }
  if (tag === "A") {
    const href = (node.getAttribute("href") || "").trim();
    const kept = (LINK.test(href) && validUrl(href)) || SITE_LINK.test(href);
    return kept ? [element("a", {href}, inner())] : inner();
  }
  if (tag === "DIV" || tag === "SECTION" || tag === "ARTICLE" || tag === "HEADER" || tag === "FOOTER") {
    // A wrapper: a paragraph if it holds only text, else its blocks.
    const holdsBlocks = [...node.children].some((child) => BLOCKS.has(child.tagName.toUpperCase()));
    return holdsBlocks ? inner() : [element("p", {}, inner())];
  }
  // Any inline element: its text, bold or italic as its style says.
  let content = inner();
  const weight = /font-weight\s*:\s*(\w+)/i.exec(style);
  const bold = weight ? (weight[1] === "bold" || Number(weight[1]) >= 600)
    : tag === "B" || tag === "STRONG";
  const fontStyle = /font-style\s*:\s*(\w+)/i.exec(style);
  const italic = fontStyle ? fontStyle[1] === "italic" : tag === "I" || tag === "EM";
  if (italic) content = [element("em", {}, content)];
  if (bold) content = [element("strong", {}, content)];
  return content;
}

// A pasted table laid out as the Editor keeps one: its merged cells undone
// (the value in the first cell a merge covers, as app.markdown_form does
// on save) and its first row the header.
// A pasted table laid out as the Editor keeps one: its merged cells undone
// (the value in the first cell a merge covers, as app.markdown_form does
// on save) and its first row the header.
function regularTables(root) {
  // Innermost first, so each table's cells are final when it is read.
  for (const table of [...root.querySelectorAll("table")].reverse()) {
    const rows = [];
    // Column -> how many more rows a merged cell above still covers.
    const covered = [];
    const coverOrPad = (cells) => {
      if (covered[cells.length] > 0) covered[cells.length] -= 1;
      cells.push([]);
    };
    for (const tr of table.rows) {
      const cells = [];
      for (const cell of tr.cells) {
        while (covered[cells.length] > 0) coverOrPad(cells);
        // The DOM keeps colSpan within 1 to 1000, as the server does.
        for (let offset = 0; offset < cell.colSpan; offset++) {
          if (cell.rowSpan > 1) covered[cells.length] = cell.rowSpan - 1;
          cells.push(offset ? [] : [...cell.childNodes]);
        }
      }
      while (covered.slice(cells.length).some((rows) => rows > 0)) coverOrPad(cells);
      rows.push(cells);
    }
    table.replaceWith(buildTable(rows));
  }
}

// Tab-separated text (a range copied as text) as rows of cell values; null
// unless every line has a tab.
export function tabSeparated(text) {
  const rows = spreadsheetRows(text);
  return rows.some((cells) => cells.length < 2) ? null : rows;
}

// A range copied from a spreadsheet as text, as rows of cell values. A
// value in double quotes may hold a line break, a tab, or a doubled
// quote, as spreadsheets write it.
export function spreadsheetRows(text) {
  text = text.replace(/\r\n?/g, "\n").replace(/\n$/, "");
  const rows = [[]];
  let value = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') {
        value += '"';
        i++;
      } else if (c === '"') {
        quoted = false;
      } else {
        value += c;
      }
    } else if (c === '"' && value === "") {
      quoted = true;
    } else if (c === "\t" || c === "\n") {
      rows[rows.length - 1].push(value);
      value = "";
      if (c === "\n") rows.push([]);
    } else {
      value += c;
    }
  }
  rows[rows.length - 1].push(value);
  return rows.map((cells) => cells.map((cell) => cell.replace(/\s+/g, " ").trim()));
}

// Word pastes a list as paragraphs, each with its marker in an
// "mso-list:Ignore" span; put each run of them back in a list.
function wordLists(root) {
  const isItem = (node) => node.tagName === "P" &&
    (/mso-list/i.test(node.getAttribute("style") || "") || /^MsoListParagraph/.test(node.className));
  const runs = [];
  for (const item of [...root.querySelectorAll("p")].filter(isItem)) {
    const run = runs[runs.length - 1];
    if (run && nextElement(run[run.length - 1]) === item) run.push(item);
    else runs.push([item]);
  }
  for (const run of runs) {
    const marker = run[0].querySelector("[style*='mso-list:Ignore' i]");
    const ordered = Boolean(marker) && /^\s*[\dA-Za-z]{1,3}[.)]/.test(marker.textContent);
    const list = run[0].ownerDocument.createElement(ordered ? "ol" : "ul");
    run[0].before(list);
    for (const item of run) {
      for (const ignored of item.querySelectorAll("[style*='mso-list:Ignore' i]")) ignored.remove();
      const li = item.ownerDocument.createElement("li");
      li.append(...item.childNodes);
      item.remove();
      list.append(li);
    }
  }
}

function nextElement(node) {
  let sibling = node.nextSibling;
  while (sibling && sibling.nodeType !== Node.ELEMENT_NODE) sibling = sibling.nextSibling;
  return sibling;
}

export function textAsHtml(text) {
  return text.split(/\r?\n\s*\r?\n/).map((paragraph) =>
    `<p>${escapeHtml(paragraph.trim()).replace(/\r?\n/g, "<br>")}</p>`).join("");
}
