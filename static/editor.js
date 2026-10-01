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
  const CHART = "[data-chart]";
  const CARD = "admin-editor-chart";
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
    // The Chart builder, made when it is first opened.
    const chartPreview = wrapper.dataset.chartPreview;
    let builder = null;

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
        <button type="button" data-action="chart">Insert chart</button>
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
    const insertChartButton = toolbar.querySelector("[data-action=chart]");
    insertChartButton.hidden = !chartPreview;
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
    for (const card of area.querySelectorAll(CHART)) chartCard(card);
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
      if (action === "chart") return openChart(null);
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
      insertChartButton.disabled = inTable;
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

    // Charts: a card in the body, edited in the Chart builder.

    let chartRange = null;

    // `card` is the card to edit, or null for a new Chart.
    function openChart(card) {
      chartRange = card ? null : currentRange();
      builder = builder || chartBuilder(chartPreview, () => form.elements.csrf_token.value);
      builder.open(card ? card.dataset.chart : null, (chart, figure) => {
        const placed = element("div", {class: CARD, "data-chart": chart});
        // The server's drawing (app.chart_drawing), safe as it is built.
        placed.innerHTML = figure;
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
        if (node.closest(`${LOCKED}, ${CHART}`)) continue;
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
      const shown = `${LOCKED}, ${CHART}`;
      if (!area.lastElementChild || area.lastElementChild.matches(shown)) {
        area.append(element("p", {}, [element("br")]));
      }
      if (area.firstElementChild.matches(shown)) area.prepend(element("p", {}, [element("br")]));
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
      for (const block of copy.querySelectorAll(`${LOCKED}, ${CHART}`)) {
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
      // Nothing in a locked block or a card is edited in place.
      return found && area.contains(found) && found !== area &&
        !found.closest(`${LOCKED}, ${CHART}`) ? found : null;
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

  // The Chart builder (spec #14, T17): a dialog with the Chart's fields and
  // a grid, categories down and series across. As the writer types, the
  // server checks the Chart and draws it (app.routes.charts), with the
  // drawing the public page has; each of its errors shows by its field or
  // cell, and Insert waits until there are none. The dialog is outside the
  // form, so nothing in it is posted with the item.

  const CHART_TYPES = [["bar", "Vertical bar"], ["hbar", "Horizontal bar"], ["line", "Line"]];
  // The grammar's limits (app.charts), for the grid's buttons and pastes.
  const MOST_CATEGORIES = {bar: 30, hbar: 30, line: 60};
  const MOST_SERIES = 4;
  const PASTE_CUT = "The paste was larger than a chart can be, so its last rows or columns were left out.";
  const NOT_DRAWN = "The chart can't be drawn right now. Reload the page (you may need to log in again).";
  // What reads as a value cell (app.charts.read_cell, roughly): for a
  // paste, telling names from numbers. The server decides what is valid.
  const MISSING_VALUES = new Set(["", "—", "n/a"]);
  const SUPPRESSED = /^(\*|(<|≤|<=)\d+)$/;
  const NUMBER = /^[-+]?\(?\$?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?%?\)?( \p{L}+([ -]\p{L}+)*)?$/u;
  let builders = 0;

  function isValue(text) {
    const typed = text.trim();
    return MISSING_VALUES.has(typed.toLowerCase()) || SUPPRESSED.test(typed) || NUMBER.test(typed);
  }

  function chartBuilder(previewPath, csrfToken) {
    const id = `admin-chart-builder-${++builders}`;
    const field = (name, label, extra = "") => `
      <p><label>${label} <input type="text" data-field="${name}" autocomplete="off"
        aria-describedby="${id}-${name}-error${extra ? ` ${id}-${name}-hint` : ""}"></label>
        ${extra ? `<small id="${id}-${name}-hint">${extra}</small>` : ""}
        <small class="admin-chart-builder-error" id="${id}-${name}-error" data-error-for="${name}"></small></p>`;
    const dialog = element("dialog", {class: "admin-chart-builder", "aria-labelledby": `${id}-heading`});
    dialog.innerHTML = `
      <h2 id="${id}-heading">Insert chart</h2>
      <p class="admin-chart-builder-message" role="alert"></p>
      <div class="admin-chart-builder-fields">
        <p><label>Type <select data-field="type" aria-describedby="${id}-type-error">
          ${CHART_TYPES.map(([value, name]) => `<option value="${value}">${name}</option>`).join("")}
        </select></label>
          <small class="admin-chart-builder-error" id="${id}-type-error" data-error-for="type"></small></p>
        <p class="admin-chart-builder-suggestion" hidden>Long category names are shortened under
          vertical bars; a horizontal bar chart shows them whole.
          <button type="button" data-builder="hbar">Use horizontal bar</button></p>
        ${field("title", "Title (required)")}
        ${field("x_label", "Category axis label")}
        ${field("y_label", "Value axis label")}
        ${field("unit", "Units", "$ goes before the numbers; %, or a word such as students, after.")}
        ${field("source", "Source or note")}
      </div>
      <h3>Data</h3>
      <p class="admin-chart-builder-hint" id="${id}-grid-hint">Categories down, series across.
        Paste a range from Excel or Sheets into any cell. Empty rows and series at the end are left out.</p>
      <div class="admin-chart-builder-grid-scroll">
        <table class="admin-chart-builder-grid" aria-describedby="${id}-grid-hint"></table>
      </div>
      <p class="admin-chart-builder-grid-tools">
        <button type="button" data-builder="add-category">Add category</button>
        <button type="button" data-builder="add-series">Add series</button></p>
      <p class="admin-chart-builder-error" data-error-for="categories"></p>
      <p class="admin-chart-builder-error" data-error-for="series"></p>
      <h3>Chart</h3>
      <div class="content-body admin-chart-builder-preview"></div>
      <p class="admin-chart-builder-actions">
        <button type="button" data-builder="insert" disabled>Insert chart</button>
        <button type="button" data-builder="cancel">Cancel</button>
        <small class="admin-chart-builder-status" role="status"></small></p>`;
    document.body.append(dialog);
    const heading = dialog.querySelector("h2");
    const messageLine = dialog.querySelector(".admin-chart-builder-message");
    const suggestion = dialog.querySelector(".admin-chart-builder-suggestion");
    const grid = dialog.querySelector(".admin-chart-builder-grid");
    const preview = dialog.querySelector(".admin-chart-builder-preview");
    const insertButton = dialog.querySelector("[data-builder=insert]");
    const statusLine = dialog.querySelector(".admin-chart-builder-status");

    // The Chart as the dialog holds it: every field as typed, and the grid's
    // rows and columns, empty ones too.
    let state = null;
    // The fields whose errors show: those typed in, left, or pasted into;
    // every one when editing a Chart.
    let touched = new Set();
    let showAll = false;
    // The server's answer for the dialog as it is now, once it has come.
    let answer = null;
    let pending = false;
    let timer = null;
    let latest = 0;
    let done = null;
    // Said once after a paste the grid couldn't hold all of.
    let pasteNote = "";

    function open(text, onInsert) {
      const chart = text ? parseJson(text, null) : null;
      state = chart ? fromChart(chart) : blankChart();
      touched = new Set();
      showAll = Boolean(chart);
      done = onInsert;
      answer = null;
      pending = true;
      pasteNote = "";
      heading.textContent = chart ? "Edit chart" : "Insert chart";
      insertButton.textContent = chart ? "Update chart" : "Insert chart";
      for (const input of dialog.querySelectorAll(".admin-chart-builder-fields [data-field]")) {
        input.value = state[input.dataset.field];
      }
      preview.replaceChildren();
      renderGrid();
      dialog.showModal();
      dialog.querySelector("[data-field=title]").focus();
      redraw(0);
    }

    function blankChart() {
      return {type: "bar", title: "", x_label: "", y_label: "", unit: "", source: "",
              categories: ["", "", ""], series: [{name: "Series 1", values: ["", "", ""]}]};
    }

    function fromChart(chart) {
      return {type: chart.type || "bar", title: chart.title || "", x_label: chart.x_label || "",
              y_label: chart.y_label || "", unit: chart.unit ? chart.unit.text : "",
              source: chart.source || "", categories: [...(chart.categories || [])],
              series: (chart.series || []).map((series) => ({name: series.name,
                                                             values: [...series.values]}))};
    }

    // The Chart's block, as the grammar has it (app.charts), less empty rows
    // and series at the end of the grid, so the fields' places are the grid's.
    function toChart() {
      const blank = (texts) => texts.every((text) => !text.trim());
      let rows = state.categories.length;
      while (rows > 1 && blank([state.categories[rows - 1],
                                ...state.series.map((series) => series.values[rows - 1])])) rows--;
      let columns = state.series.length;
      while (columns > 1 && blank([state.series[columns - 1].name,
                                   ...state.series[columns - 1].values])) columns--;
      const chart = {version: 1, type: state.type, title: state.title.trim()};
      for (const key of ["x_label", "y_label"]) if (state[key].trim()) chart[key] = state[key].trim();
      const unit = state.unit.trim();
      if (unit) chart.unit = {text: unit, position: unit === "$" ? "prefix" : "suffix"};
      if (state.source.trim()) chart.source = state.source.trim();
      chart.categories = state.categories.slice(0, rows).map((text) => text.trim());
      chart.series = state.series.slice(0, columns).map((series) => ({
        name: series.name.trim(), values: series.values.slice(0, rows).map((text) => text.trim())}));
      return JSON.stringify(chart);
    }

    function setField(name, value) {
      const [part, index, key, place] = name.split(".");
      if (part === "categories") state.categories[index] = value;
      else if (part === "series" && key === "name") state.series[index].name = value;
      else if (part === "series") state.series[index].values[place] = value;
      else state[part] = value;
    }

    // The grid.

    function renderGrid() {
      const cell = (tag, children, attributes = {}) =>
        element(tag, {class: "admin-chart-builder-cell", ...attributes}, children);
      const many = state.series.length > 1;
      const head = element("tr", {}, [cell("th", ["Category"], {scope: "col"})]);
      state.series.forEach((series, column) => {
        head.append(cell("th", [
          ...gridInput(`series.${column}.name`, series.name, `Series ${column + 1} name`),
          ...(many ? [gridButton("Remove", `Remove series ${column + 1}`,
                                 () => removeSeries(column))] : [])], {scope: "col"}));
      });
      const rows = state.categories.map((category, row) => element("tr", {}, [
        cell("td", gridInput(`categories.${row}`, category, `Category ${row + 1}`)),
        ...state.series.map((series, column) => cell("td", gridInput(
          `series.${column}.values.${row}`, series.values[row],
          `${series.name.trim() || `Series ${column + 1}`}, ${category.trim() || `category ${row + 1}`}`))),
        cell("td", state.categories.length > 1
          ? [gridButton("Remove", `Remove category ${row + 1}`, () => removeCategory(row))] : []),
      ]));
      grid.replaceChildren(element("thead", {}, [head]), element("tbody", {}, rows));
      dialog.querySelector("[data-builder=add-category]").disabled =
        state.categories.length >= MOST_CATEGORIES[state.type];
      dialog.querySelector("[data-builder=add-series]").disabled = state.series.length >= MOST_SERIES;
      showAnswer();
    }

    function gridInput(name, value, label) {
      const error = `${id}-${name.replace(/\./g, "-")}-error`;
      const input = element("input", {type: "text", "data-field": name, "aria-label": label,
                                      "aria-describedby": error, autocomplete: "off"});
      input.value = value;
      return [input, element("small", {class: "admin-chart-builder-error", id: error,
                                       "data-error-for": name})];
    }

    function gridButton(text, label, action) {
      const button = element("button", {type: "button", "aria-label": label}, [text]);
      button.addEventListener("click", action);
      return button;
    }

    function addCategory() {
      state.categories.push("");
      for (const series of state.series) series.values.push("");
    }

    function addSeries() {
      const names = new Set(state.series.map((series) => series.name.trim()));
      let number = state.series.length + 1;
      while (names.has(`Series ${number}`)) number++;
      state.series.push({name: `Series ${number}`, values: state.categories.map(() => "")});
    }

    function removeCategory(row) {
      state.categories.splice(row, 1);
      for (const series of state.series) series.values.splice(row, 1);
      changedGrid();
    }

    function removeSeries(column) {
      state.series.splice(column, 1);
      changedGrid();
    }

    function changedGrid(focus = null) {
      renderGrid();
      if (focus) dialog.querySelector(`[data-field="${focus}"]`)?.focus();
      redraw();
    }

    // A range pasted into the grid fills it from the cell pasted into. Its
    // first row is series names, and its first column category names, when
    // they aren't numbers: those go to the names, wherever it was pasted.
    grid.addEventListener("paste", (event) => {
      const input = event.target.closest("[data-field]");
      const text = event.clipboardData ? event.clipboardData.getData("text/plain") : "";
      // One value: the browser pastes it into the cell.
      if (!input || !/[\t\n\r]/.test(text.replace(/[\r\n]+$/, ""))) return;
      event.preventDefault();
      pasteRange(spreadsheetRows(text), gridPlace(input.dataset.field));
    });

    // A field's place in the grid: [row, column], the names in row and
    // column 0.
    function gridPlace(name) {
      const [part, index, key, place] = name.split(".");
      if (part === "categories") return [Number(index) + 1, 0];
      if (key === "name") return [0, Number(index) + 1];
      return [Number(place) + 1, Number(index) + 1];
    }

    function pasteRange(rows, [top, left]) {
      const seriesNames = rows[0].some((text, column) => column > 0 && text && !isValue(text));
      const categoryNames = rows.slice(seriesNames ? 1 : 0)
        .some((cells) => cells[0] && !isValue(cells[0]));
      if (seriesNames) top = 0;
      if (categoryNames) left = 0;
      let cut = false;
      rows.forEach((cells, down) => cells.forEach((text, across) => {
        const row = top + down;
        const column = left + across;
        // The corner above the category names is nobody's name.
        if (!row && !column) return;
        if (row > MOST_CATEGORIES[state.type] || column > MOST_SERIES) {
          cut = true;
          return;
        }
        while (state.categories.length < row) addCategory();
        while (state.series.length < column) addSeries();
        const name = !row ? `series.${column - 1}.name`
          : !column ? `categories.${row - 1}` : `series.${column - 1}.values.${row - 1}`;
        setField(name, text);
        touched.add(name);
      }));
      pasteNote = cut ? PASTE_CUT : "";
      changedGrid();
    }

    // Typing, and the buttons.

    dialog.addEventListener("input", (event) => {
      const name = event.target.dataset.field;
      if (!name) return;
      pasteNote = "";
      setField(name, event.target.value);
      touched.add(name);
      if (name === "type") renderGrid();
      redraw();
    });
    dialog.addEventListener("focusout", (event) => {
      const name = event.target.dataset && event.target.dataset.field;
      if (name && !touched.has(name)) {
        touched.add(name);
        showAnswer();
      }
    });
    dialog.addEventListener("click", (event) => {
      const action = event.target.closest("button[data-builder]")?.dataset.builder;
      if (action === "add-category") {
        addCategory();
        changedGrid(`categories.${state.categories.length - 1}`);
      } else if (action === "add-series") {
        addSeries();
        changedGrid(`series.${state.series.length - 1}.name`);
      } else if (action === "hbar") {
        state.type = "hbar";
        dialog.querySelector("[data-field=type]").value = "hbar";
        renderGrid();
        redraw(0);
      } else if (action === "insert" && ready()) {
        const {chart, figure} = answer;
        dialog.close();
        done(chart, figure);
      } else if (action === "cancel") {
        dialog.close();
      }
    });

    // Drawing and checking, on the server.

    function redraw(delay = 250) {
      clearTimeout(timer);
      pending = true;
      showAnswer();
      timer = setTimeout(async () => {
        const request = ++latest;
        const data = new FormData();
        data.append("csrf_token", csrfToken());
        data.append("chart", toChart());
        let found = null;
        try {
          const response = await fetch(previewPath, {method: "POST", body: data});
          // A redirect means the session ended.
          if (response.ok && !response.redirected) found = await response.json();
        } catch {}
        if (request !== latest) return;
        pending = false;
        answer = found;
        if (found && found.figure) {
          // The server's drawing (app.chart_drawing), safe as it is built.
          preview.innerHTML = found.figure;
        } else if (!preview.querySelector("figure")) {
          preview.replaceChildren(element("p", {}, ["No chart yet."]));
        }
        // The last drawing stays, faded, until the Chart is valid again, so
        // the dialog doesn't jump as the writer types.
        preview.classList.toggle("admin-chart-builder-stale", !(found && found.figure));
        showAnswer();
      }, delay);
    }

    function ready() {
      return !pending && Boolean(answer) && !answer.errors.length && Boolean(answer.chart);
    }

    function shown(name) {
      return showAll || touched.has(name);
    }

    // Each error by its field or cell, once that field's errors show; any
    // other at the top.
    function showAnswer() {
      for (const slot of dialog.querySelectorAll("[data-error-for]")) slot.textContent = "";
      for (const input of dialog.querySelectorAll("[aria-invalid]")) input.removeAttribute("aria-invalid");
      const errors = answer ? answer.errors : [];
      const others = [];
      let marked = 0;
      for (const error of errors) {
        const name = error.field || "";
        const slot = name && dialog.querySelector(`[data-error-for="${CSS.escape(name)}"]`);
        const input = name && dialog.querySelector(`[data-field="${CSS.escape(name)}"]`);
        if (slot && input) {
          if (!shown(name)) continue;
          slot.textContent = error.message;
          input.setAttribute("aria-invalid", "true");
        } else if (slot && (showAll || touched.size)) {
          slot.textContent = error.message;
        } else if (showAll || touched.size) {
          others.push(error.message);
        } else {
          continue;
        }
        marked++;
      }
      messageLine.textContent = [...(!answer && !pending ? [NOT_DRAWN] : []), ...others,
                                 pasteNote].filter(Boolean).join(" ");
      suggestion.hidden = !(answer && answer.suggestion === "hbar" && state.type === "bar");
      insertButton.disabled = !ready();
      statusLine.textContent = pending ? "Drawing…"
        : ready() || !answer ? ""
        : marked ? "Fix the marked problems to insert the chart."
        : "Add a title and data to draw the chart.";
    }

    return {open};
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
  // unless every line has a tab.
  function tabSeparated(text) {
    const rows = spreadsheetRows(text);
    return rows.some((cells) => cells.length < 2) ? null : rows;
  }

  // A range copied from a spreadsheet as text, as rows of cell values. A
  // value in double quotes may hold a line break, a tab, or a doubled
  // quote, as spreadsheets write it.
  function spreadsheetRows(text) {
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
