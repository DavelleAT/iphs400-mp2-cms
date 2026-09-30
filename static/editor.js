// The Editor (app.editor, ADR-005): the visual editor for a Data Bite's or
// Report's body, in plain JavaScript with no dependency.
//
// It takes over the body textarea of each edit and create form. If this
// script doesn't run, the textarea still posts Markdown. With it, the form
// posts the Editor's HTML as body_html, and body_dirty=1 once the writer has
// changed the body; the server sanitizes the HTML and turns it into Markdown.
// So what is cleaned here is for the writer's sake, never the site's safety.
(() => {
  "use strict";

  const LINK = /^(https:\/\/|mailto:)/i;
  const LINK_REFUSED = "A web address must start with https:// or mailto:. " +
    'For a Report or Data Bite, choose "A page on this site".';
  const PAGE_NOT_CHOSEN = "Choose a Report or Data Bite to link to.";
  // A link to a Report or Data Bite (app.site_links): stored by reference
  // and resolved when the site is published.
  const SITE_LINK = /^(data-bite|report):[0-9a-f]{32}$/;
  // How the body marks a site link that won't be a link on the site; the
  // states are app.site_links'.
  const LINK_MARKS = {draft: "Not published: will show as plain text",
                      deleted: "Item deleted", unknown: "Unknown link"};
  // T18's "Insert image" will place an uploaded chart image in the body.
  const PICTURE_REFUSED = "Pictures can't be pasted or dropped into the body. " +
    'Upload the picture under "Chart images" instead.';
  const PICTURE_DROPPED = "The pasted text had pictures, which were left out. " +
    'Upload a picture under "Chart images" instead.';
  const LOCKED = "[data-locked]";
  // The wrapper each table sits in (app.rendering), so a wide one scrolls.
  const TABLE_SCROLL = "content-table-scroll";
  // A new table's size: its header row and two more, three columns across.
  const NEW_TABLE = {rows: 3, columns: 3};
  // The Editor's blocks, and the headings pasted ones become: the title is
  // the page's only H1, and there is nothing below a Subsection.
  const HEADINGS = {H1: "h2", H2: "h2", H3: "h3", H4: "h3", H5: "h3", H6: "h3"};
  const SKIPPED = new Set(["SCRIPT", "STYLE", "TEMPLATE", "HEAD", "TITLE", "META", "LINK",
                           "IFRAME", "OBJECT", "EMBED", "SVG", "MATH", "NOSCRIPT", "BUTTON",
                           "INPUT", "SELECT", "TEXTAREA"]);
  const BLOCKS = new Set(["P", "DIV", "LI", "UL", "OL", "BLOCKQUOTE", "TABLE", "THEAD",
                          "TBODY", "TFOOT", "TR", "TH", "TD", "SECTION", "ARTICLE",
                          "HEADER", "FOOTER", "PRE", ...Object.keys(HEADINGS)]);

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
    const siteItemsByHref = new Map(siteItems.map((item) => [item.href, item]));

    // What the form posts instead of the textarea.
    const bodyHtml = hidden(form, "body_html");
    const bodyDirty = hidden(form, "body_dirty");
    bodyDirty.value = wrapper.dataset.bodyDirty === "1" ? "1" : "0";
    // Whether leaving the page would lose anything: the body, or any field.
    let unsaved = bodyDirty.value === "1";
    let leaving = false;

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
      <p class="admin-editor-message" role="alert"></p>
      <div class="content-body admin-editor-area" id="${id}" contenteditable="true"
        role="textbox" aria-multiline="true" aria-labelledby="${id}-label"></div>`;
    const area = ui.querySelector(".admin-editor-area");
    const toolbar = ui.querySelector(".admin-editor-toolbar");
    const insertTableButton = toolbar.querySelector("[data-action=table]");
    const tableTools = ui.querySelector(".admin-editor-cell-tools");
    const linkPanel = ui.querySelector(".admin-editor-link");
    const linkInput = linkPanel.querySelector("input[type=text]");
    const linkSelect = linkPanel.querySelector("select");
    const linkSite = linkPanel.querySelector(".admin-editor-link-site");
    const linkWeb = linkPanel.querySelector(".admin-editor-link-web");
    fillPicker();
    const messageLine = ui.querySelector(".admin-editor-message");

    area.append(template.content.cloneNode(true));
    for (const block of area.querySelectorAll(LOCKED)) lock(block);
    ensureParagraph();
    markLinks();
    // The item's own chart images, the only pictures the body may show.
    const ownImages = new Set(area.querySelectorAll("img"));

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
      markLinks();
      bodyDirty.value = "1";
      unsaved = true;
      sync();
    });
    form.addEventListener("input", (event) => {
      if (!linkPanel.contains(event.target)) unsaved = true;
      if (event.target !== area) message("");
    });
    form.addEventListener("change", (event) => {
      if (!linkPanel.contains(event.target)) unsaved = true;
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
      if (action === "link") return openLink();
      area.focus();
      if (action === "table") return insertTable();
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
        openLink();
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
      tableTools.hidden = !inTable;
    }

    // Tables: edited in place, the first row always the header (spec #14,
    // T15). Each change lays the table out again from its cells' contents.

    function insertTable() {
      if (closest("table")) return;
      const rows = Array.from({length: NEW_TABLE.rows},
                              () => Array.from({length: NEW_TABLE.columns}, () => []));
      const table = buildTable(rows);
      placeBlocks([tableWrapper(table)]);
      caretIn(table.rows[0].cells[0]);
      changedHere();
    }

    tableTools.addEventListener("click", (event) => {
      const action = event.target.closest("button[data-table]")?.dataset.table;
      if (!action) return;
      area.focus();
      const cell = closest("th, td");
      const table = cell && cell.closest("table");
      if (!table) return;
      const rows = [...table.rows].map((tr) => [...tr.cells].map((c) => [...c.childNodes]));
      const width = Math.max(...rows.map((row) => row.length));
      let row = [...table.rows].indexOf(cell.parentElement);
      let column = [...cell.parentElement.cells].indexOf(cell);
      if (action === "row-above" || action === "row-below") {
        if (action === "row-below") row += 1;
        rows.splice(row, 0, Array.from({length: width}, () => []));
      } else if (action === "column-left" || action === "column-right") {
        if (action === "column-right") column += 1;
        for (const cells of rows) cells.splice(column, 0, []);
      } else if (action === "remove-row") {
        rows.splice(row, 1);
        row = Math.min(row, rows.length - 1);
      } else if (action === "remove-column") {
        for (const cells of rows) cells.splice(column, 1);
        column = Math.max(0, Math.min(column, width - 2));
      }
      if (action === "remove-table" || !rows.length || !rows.some((cells) => cells.length)) {
        removeTable(table);
      } else {
        const rebuilt = buildTable(rows);
        table.replaceWith(rebuilt);
        caretIn(rebuilt.rows[row].cells[Math.min(column, rebuilt.rows[row].cells.length - 1)]);
      }
      changedHere();
      showState();
    });

    function removeTable(table) {
      const wrapper = table.parentElement;
      const block = wrapper.classList.contains(TABLE_SCROLL) && wrapper.children.length === 1
        ? wrapper : table;
      // The cursor goes to the empty paragraph after it (placeBlocks leaves
      // one), or to a new one in its place.
      const next = block.nextElementSibling;
      const empty = next && next.tagName === "P" && !next.textContent.trim() &&
        !next.querySelector("img");
      const paragraph = empty ? next : element("p", {}, [element("br")]);
      if (empty) block.remove();
      else block.replaceWith(paragraph);
      caretIn(paragraph);
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

    function caretIn(node) {
      const range = document.createRange();
      range.selectNodeContents(node);
      range.collapse(true);
      const selection = document.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
    }

    // Links.

    let linkRange = null;

    function openLink() {
      linkRange = currentRange();
      const link = closest("a");
      const href = link ? link.getAttribute("href") : "";
      const site = !link || SITE_LINK.test(href);
      linkSelect.value = site && siteItemsByHref.has(href) ? href : "";
      linkInput.value = site ? "" : href;
      linkPanel.querySelector("[data-link=remove]").hidden = !link;
      linkPanel.hidden = false;
      chooseLinkTo(site ? "site" : "web");
      (site ? linkSelect : linkInput).focus();
    }

    function chooseLinkTo(choice) {
      for (const radio of linkPanel.querySelectorAll("input[type=radio]")) {
        radio.checked = radio.value === choice;
      }
      linkSite.hidden = choice !== "site";
      linkWeb.hidden = choice !== "web";
      message("");
    }

    function linkTo() {
      return linkPanel.querySelector("input[type=radio]:checked").value;
    }

    // The picker: Reports, then Data Bites, each by title, drafts marked.
    function fillPicker() {
      linkSelect.append(element("option", {value: ""}, ["Choose one…"]));
      for (const kind of ["Report", "Data Bite"]) {
        const items = siteItems.filter((item) => item.kind === kind);
        if (!items.length) continue;
        const group = element("optgroup", {label: `${kind}s`});
        for (const item of items) {
          group.append(element("option", {value: item.href},
                               [item.draft ? `${item.title} (Draft)` : item.title]));
        }
        linkSelect.append(group);
      }
    }

    // Marks each site link in the body that won't be a link on the site.
    function markLinks() {
      for (const link of area.querySelectorAll("a")) {
        const mark = LINK_MARKS[linkState(link.getAttribute("href") || "")];
        if (mark) {
          link.dataset.linkMark = mark;
          link.title = mark;
        } else if (link.dataset.linkMark) {
          delete link.dataset.linkMark;
          link.removeAttribute("title");
        }
      }
    }

    function linkState(href) {
      if (!SITE_LINK.test(href)) return null;
      const item = siteItemsByHref.get(href);
      if (item) return item.draft ? "draft" : null;
      return linkStates[href] || "unknown";
    }

    function closeLink() {
      linkPanel.hidden = true;
      restoreRange();
    }

    function restoreRange() {
      area.focus();
      if (linkRange) {
        const selection = document.getSelection();
        selection.removeAllRanges();
        selection.addRange(linkRange);
      }
    }

    function addLink() {
      const site = linkTo() === "site";
      const href = site ? linkSelect.value : linkInput.value.trim();
      if (site && !siteItemsByHref.has(href)) {
        message(PAGE_NOT_CHOSEN);
        linkSelect.focus();
        return;
      }
      if (!site && (!LINK.test(href) || !validUrl(href))) {
        message(LINK_REFUSED);
        linkInput.focus();
        return;
      }
      // With no text chosen, the link's text is the item's title or the address.
      const text = site ? siteItemsByHref.get(href).title : href;
      linkPanel.hidden = true;
      message("");
      restoreRange();
      const link = closest("a");
      if (link) {
        link.setAttribute("href", href);
        changedHere();
      } else if (!linkRange || linkRange.collapsed) {
        command("insertHTML", `<a href="${escapeHtml(href)}">${escapeHtml(text)}</a>`);
      } else {
        command("createLink", href);
      }
      markLinks();
    }

    function removeLink() {
      linkPanel.hidden = true;
      restoreRange();
      const link = closest("a");
      if (!link) return;
      const range = document.createRange();
      range.selectNodeContents(link);
      document.getSelection().removeAllRanges();
      document.getSelection().addRange(range);
      command("unlink");
    }

    linkPanel.addEventListener("change", (event) => {
      if (event.target.type === "radio") chooseLinkTo(event.target.value);
    });
    linkPanel.addEventListener("click", (event) => {
      const action = event.target.closest("button")?.dataset.link;
      if (action === "add") addLink();
      else if (action === "remove") removeLink();
      else if (action === "cancel") closeLink();
    });
    linkPanel.addEventListener("keydown", (event) => {
      // Enter in a field adds the link rather than submitting the form; on
      // a button, it presses that button.
      if (event.key === "Enter" && event.target.tagName !== "BUTTON") {
        event.preventDefault();
        addLink();
      } else if (event.key === "Escape") {
        event.preventDefault();
        closeLink();
      }
    });

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
        if (!ownImages.has(img)) {
          img.remove();
          message(PICTURE_DROPPED);
        }
      }
      for (const node of area.querySelectorAll("[style], span, font")) {
        if (node.closest(LOCKED)) continue;
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

    function ensureParagraph() {
      if (!area.querySelector(":scope > :not([data-locked])")) area.append(element("p", {}, [element("br")]));
    }

    function changedHere() {
      // A change made here, not by the browser: tell the form, as the
      // browser does for its own, so the Site preview follows it too.
      area.dispatchEvent(new InputEvent("input", {bubbles: true}));
    }

    function sync() {
      bodyHtml.value = posted();
    }

    // The body as posted: each locked block empty, since what it shows is
    // only for display, and at the top level, where the server takes it.
    function posted() {
      const copy = area.cloneNode(true);
      for (const block of copy.querySelectorAll(LOCKED)) {
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
      return copy.innerHTML;
    }

    function closest(selector) {
      const node = document.getSelection().anchorNode;
      const start = node && (node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement);
      const found = start && start.closest(selector);
      return found && area.contains(found) && found !== area ? found : null;
    }

    function currentRange() {
      const selection = document.getSelection();
      if (!selection.rangeCount) return null;
      const range = selection.getRangeAt(0);
      return area.contains(range.commonAncestorContainer) ? range.cloneRange() : null;
    }

    function message(text) {
      messageLine.textContent = text;
    }
  }

  // Cleaning a paste: only what the Editor supports survives.

  // The cleaned paste, as the children of a <div>.
  function cleanPasted(html) {
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
  function asBlocks(nodes) {
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

  // A table of `rows`, each a list of cells' contents: the first row the
  // header, every row as wide as the widest, and an empty cell holding a
  // line break so the cursor can go in it.
  function buildTable(rows) {
    const width = Math.max(1, ...rows.map((cells) => cells.length));
    const cell = (tag, content) => element(tag, {}, content.length ? content : [element("br")]);
    const row = (tag, cells) => element("tr", {}, Array.from({length: width},
                                                              (_, i) => cell(tag, cells[i] || [])));
    const [header = [], ...body] = rows;
    return element("table", {}, [element("thead", {}, [row("th", header)]),
                                 element("tbody", {}, body.map((cells) => row("td", cells)))]);
  }

  function tableWrapper(table) {
    return element("div", {class: TABLE_SCROLL}, [table]);
  }

  // Tab-separated text (a range copied as text) as rows of cell values; null
  // unless every line has a tab. A value in double quotes may hold a line
  // break, a tab, or a doubled quote, as spreadsheets write it.
  function tabSeparated(text) {
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
    if (rows.some((cells) => cells.length < 2)) return null;
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

  function textAsHtml(text) {
    return text.split(/\r?\n\s*\r?\n/).map((paragraph) =>
      `<p>${escapeHtml(paragraph.trim()).replace(/\r?\n/g, "<br>")}</p>`).join("");
  }

  function validUrl(href) {
    try {
      new URL(href);
      return true;
    } catch {
      return false;
    }
  }

  function parseJson(text, fallback) {
    try {
      return text ? JSON.parse(text) : fallback;
    } catch {
      return fallback;
    }
  }

  function hasFiles(transfer) {
    return Boolean(transfer) && [...transfer.types].includes("Files");
  }

  function hidden(form, name) {
    const input = element("input", {type: "hidden", name});
    form.append(input);
    return input;
  }

  function element(tag, attributes = {}, children = []) {
    const node = document.createElement(tag);
    for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value);
    node.append(...children);
    return node;
  }

  function escapeHtml(text) {
    return text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
  }
})();
