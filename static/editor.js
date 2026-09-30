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
  const LINK_REFUSED = "Links must start with https:// or mailto:.";
  // T18's "Insert image" will place an uploaded chart image in the body.
  const PICTURE_REFUSED = "Pictures can't be pasted or dropped into the body. " +
    'Upload the picture under "Chart images" instead.';
  const PICTURE_DROPPED = "The pasted text had pictures, which were left out. " +
    'Upload a picture under "Chart images" instead.';
  const LOCKED = "[data-locked]";
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
      </div>
      <div class="admin-editor-link" hidden>
        <label>Link address <input type="text" inputmode="url" autocomplete="off"
          placeholder="https://" aria-describedby="${id}-link-hint"></label>
        <button type="button" data-link="add">Add link</button>
        <button type="button" data-link="remove">Remove link</button>
        <button type="button" data-link="cancel">Cancel</button>
        <small id="${id}-link-hint">A web address (https://) or an email address (mailto:).</small>
      </div>
      <p class="admin-editor-message" role="alert"></p>
      <div class="content-body admin-editor-area" id="${id}" contenteditable="true"
        role="textbox" aria-multiline="true" aria-labelledby="${id}-label"></div>`;
    const area = ui.querySelector(".admin-editor-area");
    const toolbar = ui.querySelector(".admin-editor-toolbar");
    const linkPanel = ui.querySelector(".admin-editor-link");
    const linkInput = linkPanel.querySelector("input");
    const messageLine = ui.querySelector(".admin-editor-message");

    area.append(template.content.cloneNode(true));
    for (const block of area.querySelectorAll(LOCKED)) lock(block);
    ensureParagraph();
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
      bodyDirty.value = "1";
      unsaved = true;
      sync();
    });
    form.addEventListener("input", (event) => {
      if (!linkPanel.contains(event.target)) unsaved = true;
      if (event.target !== area) message("");
    });
    form.addEventListener("change", () => { unsaved = true; });
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
    toolbar.addEventListener("mousedown", (event) => {
      if (event.target.closest("button")) event.preventDefault();
    });
    toolbar.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-action]");
      if (!button) return;
      const action = button.dataset.action;
      if (action === "link") return openLink();
      area.focus();
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
      for (const button of toolbar.querySelectorAll("[data-action]")) {
        button.setAttribute("aria-pressed", String(pressed[button.dataset.action]));
      }
    }

    // Links.

    let linkRange = null;

    function openLink() {
      linkRange = currentRange();
      const link = closest("a");
      linkInput.value = link ? link.getAttribute("href") : "";
      linkPanel.querySelector("[data-link=remove]").hidden = !link;
      linkPanel.hidden = false;
      linkInput.focus();
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
      const href = linkInput.value.trim();
      if (!LINK.test(href) || !validUrl(href)) {
        message(LINK_REFUSED);
        linkInput.focus();
        return;
      }
      linkPanel.hidden = true;
      message("");
      restoreRange();
      const link = closest("a");
      if (link) {
        link.setAttribute("href", href);
        changedHere();
      } else if (!linkRange || linkRange.collapsed) {
        // No text chosen: the address is the link's text.
        command("insertHTML", `<a href="${escapeHtml(href)}">${escapeHtml(href)}</a>`);
      } else {
        command("createLink", href);
      }
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

    linkPanel.addEventListener("click", (event) => {
      const action = event.target.closest("button")?.dataset.link;
      if (action === "add") addLink();
      else if (action === "remove") removeLink();
      else if (action === "cancel") closeLink();
    });
    linkInput.addEventListener("keydown", (event) => {
      // Enter adds the link rather than submitting the form.
      if (event.key === "Enter") {
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
      if (html) {
        const cleaned = cleanPasted(html);
        if (cleaned.droppedPicture) message(PICTURE_DROPPED);
        if (cleaned.html) command("insertHTML", cleaned.html);
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

  function cleanPasted(html) {
    // DOMParser's document is inert: no script runs and nothing loads.
    const source = new DOMParser().parseFromString(html, "text/html");
    wordLists(source.body);
    const state = {droppedPicture: false};
    const out = document.createElement("div");
    for (const node of [...source.body.childNodes]) out.append(...clean(node, state));
    return {html: out.innerHTML, droppedPicture: state.droppedPicture};
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
    if (["P", "UL", "OL", "BLOCKQUOTE", "TABLE", "THEAD", "TBODY", "TFOOT", "TR", "TH", "TD"]
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
      return LINK.test(href) && validUrl(href) ? [element("a", {href}, inner())] : inner();
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
