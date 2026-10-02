import {LINK, SITE_LINK, element, escapeHtml, validUrl} from "./editor-dom.js";

// Links in the Editor's body (static/editor.js): to a Report or Data Bite,
// chosen by title and stored by reference, or to a web or email address.

const LINK_REFUSED = "A web address must start with https:// or mailto:. " +
  'For a Report or Data Bite, choose "A page on this site".';
const PAGE_NOT_CHOSEN = "Choose a Report or Data Bite to link to.";
// How the body marks a site link that won't be a link on the site; the
// states are app.site_links'.
const LINK_MARKS = {draft: "Not published: will show as plain text",
                    deleted: "Item deleted", unknown: "Unknown link"};

// `ed` is the Editor the link panel is in. `siteItems` are the Reports and
// Data Bites a link may lead to, and `linkStates` the state of each site
// link in the stored body that won't resolve.
export function linkPanel(ed, siteItems, linkStates) {
  const {area, message, closest, currentRange, restoreRange, command, changedHere} = ed;
  const siteItemsByHref = new Map(siteItems.map((item) => [item.href, item]));
  const panel = ed.ui.querySelector(".admin-editor-link");
  const linkInput = panel.querySelector("input[type=text]");
  const linkSelect = panel.querySelector("select");
  const linkSite = panel.querySelector(".admin-editor-link-site");
  const linkWeb = panel.querySelector(".admin-editor-link-web");
  fillPicker();

  let linkRange = null;

  function openLink() {
    ed.images.close();
    linkRange = currentRange();
    const link = closest("a");
    const href = link ? link.getAttribute("href") : "";
    const site = !link || SITE_LINK.test(href);
    linkSelect.value = site && siteItemsByHref.has(href) ? href : "";
    linkInput.value = site ? "" : href;
    panel.querySelector("[data-link=remove]").hidden = !link;
    panel.hidden = false;
    chooseLinkTo(site ? "site" : "web");
    (site ? linkSelect : linkInput).focus();
  }

  function chooseLinkTo(choice) {
    for (const radio of panel.querySelectorAll("input[type=radio]")) {
      radio.checked = radio.value === choice;
    }
    linkSite.hidden = choice !== "site";
    linkWeb.hidden = choice !== "web";
    message("");
  }

  function linkTo() {
    return panel.querySelector("input[type=radio]:checked").value;
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
    panel.hidden = true;
    restoreRange(linkRange);
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
    panel.hidden = true;
    message("");
    restoreRange(linkRange);
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
    panel.hidden = true;
    restoreRange(linkRange);
    const link = closest("a");
    if (!link) return;
    const range = document.createRange();
    range.selectNodeContents(link);
    document.getSelection().removeAllRanges();
    document.getSelection().addRange(range);
    command("unlink");
  }

  panel.addEventListener("change", (event) => {
    if (event.target.type === "radio") chooseLinkTo(event.target.value);
  });
  panel.addEventListener("click", (event) => {
    const action = event.target.closest("button")?.dataset.link;
    if (action === "add") addLink();
    else if (action === "remove") removeLink();
    else if (action === "cancel") closeLink();
  });
  panel.addEventListener("keydown", (event) => {
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

  return {
    open: openLink,
    mark: markLinks,
    hide: () => { panel.hidden = true; },
    contains: (node) => panel.contains(node),
  };
}
