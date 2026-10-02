// The Editor (app.editor, ADR-005): the visual editor for a Data Bite's or
// Report's body, in plain JavaScript with no dependency.
//
// It takes over the body textarea of each edit and create form. If this
// script doesn't run, the textarea still posts Markdown. With it, the form
// posts the Editor's HTML as body_html, and body_dirty=1 once the writer has
// changed the body; the server sanitizes the HTML and turns it into Markdown.
// So what is cleaned here is for the writer's sake, never the site's safety.
//
// A Chart (T17) is a card in the body, its block in data-chart and its
// drawing from the server. "Insert chart" and a card's "Edit chart" open the
// Chart builder, which the server draws and checks as the writer types.
//
// A chart image (T18) is one of the item's uploaded pictures, from its admin
// route. "Insert image" puts one in the body with a description, which it
// requires; clicking one in the body changes its description or removes it.
//
// This file is the Editor's core: the toolbar, Charts, paste and drop, and
// locked blocks. Its other parts are modules beside it: editor-dom.js (what
// they share), editor-tables.js, editor-links.js, editor-images.js,
// editor-paste.js, and editor-chart-builder.js.

import {BLOCKS, CHART, LOCKED, SHOWN_ONLY, buildTable, element, hasFiles, hidden, parseJson,
        tableWrapper} from "./editor-dom.js";
import {asBlocks, cleanPasted, tabSeparated, textAsHtml} from "./editor-paste.js";
import {chartBuilder} from "./editor-chart-builder.js";
import {imagePanel} from "./editor-images.js";
import {linkPanel} from "./editor-links.js";
import {tables} from "./editor-tables.js";

// A picture reaches the body only as an uploaded chart image, by "Insert image".
const PICTURE_REFUSED = "Pictures can't be pasted or dropped into the body. " +
  'Upload the picture under "Chart images", then use "Insert image".';
const PICTURE_DROPPED = "The pasted text had pictures, which were left out. " +
  'Upload a picture under "Chart images", then use "Insert image".';
const CARD = "admin-editor-chart";

let editors = 0;
for (const wrapper of document.querySelectorAll(".admin-editor")) takeOver(wrapper);

function takeOver(wrapper) {
  const form = wrapper.closest("form");
  const textarea = wrapper.querySelector("textarea[name=body]");
  const template = wrapper.querySelector("template.admin-editor-content");
  if (!form || !textarea || !template) return;
  const id = `admin-editor-${++editors}`;
  // The Reports and Data Bites a link may lead to, and the state of each
  // site link in the stored body that won't resolve.
  const siteItems = parseJson(wrapper.dataset.siteItems, []);
  const linkStates = parseJson(wrapper.dataset.linkStates, {});
  // The Chart builder, made when it is first opened.
  const chartPreview = wrapper.dataset.chartPreview;
  let builder = null;
  // The item's chart images ({name, src}), or null on a create page, where
  // there is no item to hold one yet.
  const imageList = "images" in wrapper.dataset ? parseJson(wrapper.dataset.images, []) : null;

  // What the form posts instead of the textarea.
  const bodyHtml = hidden(form, "body_html");
  const bodyDirty = hidden(form, "body_dirty");
  bodyDirty.value = wrapper.dataset.bodyDirty === "1" ? "1" : "0";
  // Whether leaving the page would lose anything: the body, or any field.
  // The form hears when it first would, for the save bar's "Unsaved
  // changes" (admin/_save_bar.html).
  let unsaved = false;
  let leaving = false;
  const markUnsaved = () => {
    if (!unsaved) form.dispatchEvent(new CustomEvent("admin-editor-unsaved"));
    unsaved = true;
  };
  // A page re-shown after a refused save holds values never saved, body
  // or not (admin/_content_fields.html).
  if (bodyDirty.value === "1" || form.dataset.unsaved === "1") markUnsaved();

  const ui = element("div", {class: "admin-editor-ui"});
  ui.innerHTML = `
    <p class="admin-editor-label" id="${id}-label">Body</p>
    <div class="admin-editor-toolbar" role="toolbar" aria-label="Formatting" aria-controls="${id}">
      <button type="button" data-action="bold" aria-pressed="false"><b>Bold</b></button>
      <button type="button" data-action="italic" aria-pressed="false"><i>Italic</i></button>
      <button type="button" data-action="bullets" aria-pressed="false">Bulleted list</button>
      <button type="button" data-action="numbers" aria-pressed="false">Numbered list</button>
      <button type="button" data-action="link" aria-pressed="false">Link</button>
      <button type="button" data-action="h2" aria-pressed="false">Section</button>
      <button type="button" data-action="h3" aria-pressed="false">Subsection</button>
      <button type="button" data-action="quote" aria-pressed="false">Quote</button>
      <button type="button" data-action="table">Insert table</button>
      <button type="button" data-action="chart">Insert chart</button>
      <button type="button" data-action="image">Insert image</button>
    </div>
    <div class="admin-editor-cell-tools" role="toolbar" aria-label="Table" aria-controls="${id}" hidden>
      <button type="button" data-table="row-above">Row above</button>
      <button type="button" data-table="row-below">Row below</button>
      <button type="button" data-table="column-left">Column left</button>
      <button type="button" data-table="column-right">Column right</button>
      <button type="button" data-table="remove-row">Remove row</button>
      <button type="button" data-table="remove-column">Remove column</button>
      <button type="button" data-table="remove-table">Remove table</button>
    </div>
    <fieldset class="admin-editor-link" hidden>
      <legend>Link to</legend>
      <p class="admin-editor-link-choice">
        <label><input type="radio" name="${id}-link-to" value="site" checked> A page on this site</label>
        <label><input type="radio" name="${id}-link-to" value="web"> A web address</label>
      </p>
      <p class="admin-editor-link-site">
        <label>Report or Data Bite <select></select></label>
        <small>A draft shows as plain text until it is published.</small>
      </p>
      <p class="admin-editor-link-web" hidden>
        <label>Web address <input type="text" inputmode="url" autocomplete="off"
          placeholder="https://" aria-describedby="${id}-link-hint"></label>
        <small id="${id}-link-hint">A web address (https://) or an email address (mailto:).</small>
      </p>
      <p class="admin-editor-link-actions">
        <button type="button" data-link="add">Add link</button>
        <button type="button" data-link="remove">Remove link</button>
        <button type="button" data-link="cancel">Cancel</button>
      </p>
    </fieldset>
    <fieldset class="admin-editor-image" hidden>
      <legend>Insert image</legend>
      <p class="admin-editor-image-note"></p>
      <fieldset class="admin-editor-image-choices">
        <legend>Chart image</legend>
      </fieldset>
      <p class="admin-editor-image-description">
        <label>Description (required) <input type="text" autocomplete="off"
          aria-describedby="${id}-image-hint"></label>
        <small id="${id}-image-hint">What the chart shows, for readers who can't see it,
          e.g. "Fall enrollment by class, 2022 to 2026".</small>
      </p>
      <p class="admin-editor-image-actions">
        <button type="button" data-image="apply" disabled>Insert image</button>
        <button type="button" data-image="remove">Remove image</button>
        <button type="button" data-image="cancel">Cancel</button>
      </p>
    </fieldset>
    <p class="admin-editor-message" role="alert"></p>
    <div class="content-body admin-editor-area" id="${id}" contenteditable="true"
      role="textbox" aria-multiline="true" aria-labelledby="${id}-label"></div>`;
  const area = ui.querySelector(".admin-editor-area");
  const toolbar = ui.querySelector(".admin-editor-toolbar");
  const insertTableButton = toolbar.querySelector("[data-action=table]");
  const insertChartButton = toolbar.querySelector("[data-action=chart]");
  insertChartButton.hidden = !chartPreview;
  const tableTools = ui.querySelector(".admin-editor-cell-tools");
  const messageLine = ui.querySelector(".admin-editor-message");
  // What the Editor's modules share.
  const ed = {id, ui, area, tableTools, message, changedHere, closest, currentRange,
              restoreRange, command, showState, placeBlocks, ensureParagraph};

  area.append(template.content.cloneNode(true));
  for (const block of area.querySelectorAll(LOCKED)) lock(block);
  for (const card of area.querySelectorAll(CHART)) chartCard(card);
  ensureParagraph();
  const table = tables(ed);
  const links = ed.links = linkPanel(ed, siteItems, linkStates);
  const images = ed.images = imagePanel(ed, imageList);
  links.mark();

  // The textarea stays in the page, unposted, in case this script fails
  // part way: the form still has a body field.
  const textareaField = textarea.closest("p");
  textareaField.hidden = true;
  textarea.required = false;
  textarea.disabled = true;
  textareaField.after(ui);
  document.execCommand("defaultParagraphSeparator", false, "p");
  document.execCommand("styleWithCSS", false, false);
  sync();

  // Changes.

  area.addEventListener("input", (event) => {
    if (event.inputType === "insertFromDrop") tidyDropped();
    links.mark();
    bodyDirty.value = "1";
    markUnsaved();
    sync();
  });
  // The link and image panels' fields are only a way to change the body.
  const inPanel = (target) => links.contains(target) || images.contains(target);
  form.addEventListener("input", (event) => {
    if (!inPanel(event.target)) markUnsaved();
    if (event.target !== area) message("");
  });
  form.addEventListener("change", (event) => {
    if (!inPanel(event.target)) markUnsaved();
  });
  form.addEventListener("submit", (event) => {
    sync();
    // "Preview on site" opens a new tab and leaves this page as it is.
    if (!event.submitter || event.submitter.formTarget !== "_blank") leaving = true;
  });
  window.addEventListener("beforeunload", (event) => {
    if (unsaved && !leaving) {
      event.preventDefault();
      event.returnValue = "";
    }
  });

  // The toolbar.

  // Pressing a button keeps the selection in the body.
  for (const bar of [toolbar, tableTools]) {
    bar.addEventListener("mousedown", (event) => {
      if (event.target.closest("button")) event.preventDefault();
    });
  }
  toolbar.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const action = button.dataset.action;
    if (action === "link") return links.open();
    if (action === "chart") return openChart(null);
    if (action === "image") return images.open(null);
    area.focus();
    if (action === "table") return table.insert();
    if (action === "bold" || action === "italic") command(action);
    else if (action === "bullets") command("insertUnorderedList");
    else if (action === "numbers") command("insertOrderedList");
    else if (action === "quote") toggleQuote();
    else toggleHeading(action);
    showState();
  });
  document.addEventListener("selectionchange", showState);
  area.addEventListener("keydown", (event) => {
    if (!(event.metaKey || event.ctrlKey) || event.altKey) return;
    const key = event.key.toLowerCase();
    // Markdown can't hold an underline.
    if (key === "u") event.preventDefault();
    if (key === "k") {
      event.preventDefault();
      links.open();
    }
  });

  function command(name, value = null) {
    document.execCommand(name, false, value);
  }

  function toggleHeading(tag) {
    const block = closest("h2, h3");
    command("formatBlock", block && block.tagName.toLowerCase() === tag ? "<p>" : `<${tag}>`);
  }

  function toggleQuote() {
    const quote = closest("blockquote");
    if (!quote) return command("formatBlock", "<blockquote>");
    // Its blocks go back into the body, each a paragraph at least.
    const blocks = [];
    let run = null;
    for (const node of [...quote.childNodes]) {
      if (node.nodeType === Node.ELEMENT_NODE && BLOCKS.has(node.tagName)) {
        blocks.push(node);
        run = null;
      } else {
        if (!run) blocks.push(run = element("p"));
        run.append(node);
      }
    }
    quote.replaceWith(...blocks);
    changedHere();
  }

  function showState() {
    if (!area.contains(document.getSelection().anchorNode)) return;
    const pressed = {
      // What the body will save, not how the text looks: a heading looks
      // bold, but isn't bold text.
      bold: Boolean(closest("b, strong")), italic: Boolean(closest("i, em")),
      bullets: Boolean(closest("ul")), numbers: Boolean(closest("ol")),
      link: Boolean(closest("a")), h2: Boolean(closest("h2")), h3: Boolean(closest("h3")),
      quote: Boolean(closest("blockquote")),
    };
    for (const button of toolbar.querySelectorAll("[data-action][aria-pressed]")) {
      button.setAttribute("aria-pressed", String(pressed[button.dataset.action]));
    }
    // A table can't hold another, and its controls show only inside one.
    const inTable = Boolean(closest("table"));
    insertTableButton.disabled = inTable;
    insertChartButton.disabled = inTable;
    tableTools.hidden = !inTable;
  }

  // Puts blocks in the body after the block the cursor is in (in place of
  // it, if that is an empty paragraph), not inside it: a table is never
  // in a paragraph, list, or quote. A paragraph follows, to write on in.
  function placeBlocks(blocks) {
    const range = currentRange();
    let top = range ? range.startContainer : null;
    while (top && top.parentNode !== area) top = top.parentNode;
    if (top && top.nodeType === Node.ELEMENT_NODE && top.tagName === "P" &&
        !top.textContent.trim() && !top.querySelector("img")) {
      top.replaceWith(...blocks);
    } else if (top) {
      top.after(...blocks);
    } else {
      area.append(...blocks);
    }
    const last = blocks[blocks.length - 1];
    if (!last.nextElementSibling || last.nextElementSibling.tagName !== "P") {
      last.after(element("p", {}, [element("br")]));
    }
  }

  // Charts: a card in the body, edited in the Chart builder.

  let chartRange = null;

  // `card` is the card to edit, or null for a new Chart.
  function openChart(card) {
    links.hide();
    images.close(false);
    chartRange = card ? null : currentRange();
    builder = builder || chartBuilder(chartPreview, () => form.elements.csrf_token.value);
    builder.open(card ? card.dataset.chart : null, (chart, drawing) => {
      const placed = element("div", {class: CARD, "data-chart": chart});
      // The server's drawing (app.chart_drawing), safe as it is built.
      placed.innerHTML = drawing;
      chartCard(placed);
      area.focus();
      if (card) {
        card.replaceWith(placed);
      } else {
        if (chartRange) {
          document.getSelection().removeAllRanges();
          document.getSelection().addRange(chartRange);
        }
        placeBlocks([placed]);
      }
      changedHere();
    });
  }

  // A card is shown, not edited in place: Edit opens the builder on it.
  function chartCard(card) {
    card.contentEditable = "false";
    const edit = element("button", {type: "button"}, ["Edit chart"]);
    const remove = element("button", {type: "button"}, ["Remove chart"]);
    edit.addEventListener("click", () => openChart(card));
    remove.addEventListener("click", () => {
      card.remove();
      ensureParagraph();
      changedHere();
    });
    card.prepend(element("p", {class: "admin-editor-chart-tools"}, [edit, remove]));
  }

  // Paste and drop.

  area.addEventListener("paste", (event) => {
    const data = event.clipboardData;
    if (!data) return;
    event.preventDefault();
    const html = data.getData("text/html");
    const text = data.getData("text/plain");
    // In a table cell, a paste is its text on one line: a cell holds no
    // blocks, and a Markdown table row is one line.
    if (closest("th, td")) {
      if (text) command("insertText", text.replace(/\s+/g, " ").trim());
      return;
    }
    const rows = !html && text ? tabSeparated(text) : null;
    if (html) {
      const cleaned = cleanPasted(html);
      if (cleaned.droppedPicture) message(PICTURE_DROPPED);
      if (cleaned.html.querySelector("table")) {
        placeBlocks(asBlocks([...cleaned.html.childNodes]));
        changedHere();
      } else if (cleaned.html.innerHTML) {
        command("insertHTML", cleaned.html.innerHTML);
      }
    } else if (rows) {
      placeBlocks([tableWrapper(buildTable(rows.map((cells) =>
        cells.map((value) => value ? [document.createTextNode(value)] : []))))]);
      changedHere();
    } else if (text) {
      command("insertHTML", textAsHtml(text));
    } else if ([...data.items].some((item) => item.kind === "file")) {
      message(PICTURE_REFUSED);
    }
  });
  area.addEventListener("dragover", (event) => {
    if (hasFiles(event.dataTransfer)) event.preventDefault();
  });
  area.addEventListener("drop", (event) => {
    if (hasFiles(event.dataTransfer)) {
      event.preventDefault();
      message(PICTURE_REFUSED);
    }
  });

  // Text dragged in from elsewhere keeps only what the Editor supports.
  function tidyDropped() {
    for (const img of area.querySelectorAll("img")) {
      const own = images.ownSrc(img.src);
      if (own) {
        img.setAttribute("src", own);
      } else {
        img.remove();
        message(PICTURE_DROPPED);
      }
    }
    for (const node of area.querySelectorAll("[style], span, font")) {
      if (node.closest(SHOWN_ONLY)) continue;
      if (node.tagName === "SPAN" || node.tagName === "FONT") node.replaceWith(...node.childNodes);
      else node.removeAttribute("style");
    }
  }

  // Locked blocks: shown, not edited, and removable whole.

  function lock(block) {
    block.contentEditable = "false";
    const remove = element("button", {type: "button", class: "admin-editor-locked-remove"});
    remove.textContent = "Remove";
    remove.addEventListener("click", () => {
      block.remove();
      ensureParagraph();
      changedHere();
    });
    (block.querySelector(".admin-editor-locked-note") || block).append(" ", remove);
  }

  // Helpers.

  // The cursor can't go into a locked block or a card, so the body never
  // starts or ends with one: there is always a paragraph to write in. An
  // empty paragraph isn't saved.
  function ensureParagraph() {
    if (!area.lastElementChild || area.lastElementChild.matches(SHOWN_ONLY)) {
      area.append(element("p", {}, [element("br")]));
    }
    if (area.firstElementChild.matches(SHOWN_ONLY)) area.prepend(element("p", {}, [element("br")]));
  }

  function changedHere() {
    // A change made here, not by the browser: tell the form, as the
    // browser does for its own, so the Site preview follows it too.
    area.dispatchEvent(new InputEvent("input", {bubbles: true}));
  }

  function sync() {
    bodyHtml.value = posted();
  }

  // The body as posted: each locked block and card empty, since what it
  // shows is only for display, and at the top level, where the server
  // takes it.
  function posted() {
    const copy = area.cloneNode(true);
    for (const block of copy.querySelectorAll(SHOWN_ONLY)) {
      let top = block;
      while (top.parentNode !== copy) top = top.parentNode;
      if (top !== block) top.after(block);
      block.replaceChildren();
      block.removeAttribute("contenteditable");
    }
    // Marks are for the writer; the server keeps only a link's href anyway.
    for (const link of copy.querySelectorAll("a[data-link-mark]")) {
      delete link.dataset.linkMark;
      link.removeAttribute("title");
    }
    for (const img of copy.querySelectorAll("img[class]")) img.removeAttribute("class");
    return copy.innerHTML;
  }

  function closest(selector) {
    const node = document.getSelection().anchorNode;
    const start = node && (node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement);
    const found = start && start.closest(selector);
    // Nothing in a locked block or a card is edited in place.
    return found && area.contains(found) && found !== area &&
      !found.closest(SHOWN_ONLY) ? found : null;
  }

  function currentRange() {
    const selection = document.getSelection();
    if (!selection.rangeCount) return null;
    const range = selection.getRangeAt(0);
    return area.contains(range.commonAncestorContainer) ? range.cloneRange() : null;
  }

  // Back to the body, with the selection a panel was opened on.
  function restoreRange(range) {
    area.focus();
    if (range) {
      const selection = document.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
    }
  }

  function message(text) {
    messageLine.textContent = text;
  }
}
