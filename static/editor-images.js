import {SHOWN_ONLY, caretIn, element} from "./editor-dom.js";

// Chart images in the Editor's body (static/editor.js, T18): inserted from
// the item's own uploads, each with a description, which is required.
// Clicking one in the body changes its description or removes it.

const IMAGES_AFTER_SAVE = "Images can be added after the first save. Save this draft, " +
  'then upload a chart image under "Chart images" on its edit page.';
const NO_IMAGES = 'There are no chart images yet. Upload one under "Chart images", ' +
  "below the form, then insert it here.";
const IMAGE_NOT_CHOSEN = "Choose an image to insert.";
const DESCRIPTION_NEEDED = "Describe what the chart shows, for readers who can't see it.";

// `ed` is the Editor the image panel is in. `images` are the item's chart
// images ({name, src}), or null on a create page, where there is no item
// to hold one yet.
export function imagePanel(ed, images) {
  const {area, message, currentRange, restoreRange, placeBlocks, changedHere,
         ensureParagraph} = ed;
  const panel = ed.ui.querySelector(".admin-editor-image");
  const imageLegend = panel.querySelector("legend");
  const imageNote = panel.querySelector(".admin-editor-image-note");
  const imageChoices = panel.querySelector(".admin-editor-image-choices");
  const imageDescription = panel.querySelector(".admin-editor-image-description");
  const descriptionInput = imageDescription.querySelector("input");
  const applyImageButton = panel.querySelector("[data-image=apply]");
  const removeImageButton = panel.querySelector("[data-image=remove]");
  fillImageChoices();
  // The chart images in the body, the only pictures a drop may keep (an
  // image moved within it), by full URL: a browser may give a dragged
  // picture's src in full. Not the panel's thumbnails, which have no
  // description: an image comes in by "Insert image", described.
  const ownImages = new Map();
  for (const img of area.querySelectorAll("img")) ownImage(img.getAttribute("src"));

  let imageRange = null;
  // The image in the body being changed, or null when inserting one.
  let chosenImage = null;

  function fillImageChoices() {
    for (const image of images || []) {
      const thumbnail = element("img", {src: image.src, alt: "", loading: "lazy", draggable: "false"});
      imageChoices.append(element("label", {class: "admin-editor-image-choice"}, [
        element("input", {type: "radio", name: `${ed.id}-image`, value: image.src}),
        thumbnail, element("span", {}, [image.name])]));
    }
  }

  // `img` is an image in the body to change, or null to insert one.
  function openImage(img) {
    ed.links.hide();
    closeImagePanel(false);
    imageRange = img ? null : currentRange();
    chosenImage = img;
    // Why there is nothing to insert, if there isn't.
    let note = "";
    if (!img && images === null) note = IMAGES_AFTER_SAVE;
    else if (!img && !images.length) note = NO_IMAGES;
    // Inserting, with images to choose from.
    const choosing = !img && !note;
    imageLegend.textContent = img ? "Image" : "Insert image";
    imageNote.textContent = note;
    imageNote.hidden = !note;
    imageChoices.hidden = !choosing;
    imageDescription.hidden = Boolean(note);
    applyImageButton.hidden = Boolean(note);
    applyImageButton.textContent = img ? "Update description" : "Insert image";
    removeImageButton.hidden = !img;
    for (const radio of imageChoices.querySelectorAll("input")) {
      radio.checked = choosing && images.length === 1;
    }
    descriptionInput.value = img ? img.getAttribute("alt") || "" : "";
    if (img) img.classList.add("admin-editor-image-chosen");
    panel.hidden = false;
    showImageState();
    const first = imageChoices.querySelector("input");
    if (note) panel.querySelector("[data-image=cancel]").focus();
    else if (choosing && images.length > 1) first.focus();
    else descriptionInput.focus();
  }

  function ownImage(src) {
    ownImages.set(new URL(src, document.baseURI).href, src);
  }

  function closeImagePanel(restore = true) {
    if (chosenImage) chosenImage.classList.remove("admin-editor-image-chosen");
    chosenImage = null;
    if (panel.hidden) return;
    panel.hidden = true;
    if (restore) restoreRange(imageRange);
  }

  function chosenSrc() {
    return imageChoices.querySelector("input:checked")?.value || null;
  }

  // A description is required: Insert (or Update) waits for one.
  function showImageState() {
    const described = Boolean(descriptionInput.value.trim());
    applyImageButton.disabled = !described || (!chosenImage && !chosenSrc());
  }

  function applyImage() {
    const description = descriptionInput.value.trim().replace(/\s+/g, " ");
    const src = chosenImage ? chosenImage.getAttribute("src") : chosenSrc();
    if (!src) {
      message(IMAGE_NOT_CHOSEN);
      return imageChoices.querySelector("input")?.focus();
    }
    if (!description) {
      message(DESCRIPTION_NEEDED);
      return descriptionInput.focus();
    }
    message("");
    const img = chosenImage;
    closeImagePanel();
    if (img) {
      img.setAttribute("alt", description);
    } else {
      // A paragraph of its own, after the one the cursor is in.
      ownImage(src);
      const paragraph = element("p", {}, [element("img", {src, alt: description})]);
      placeBlocks([paragraph]);
      caretIn(paragraph.nextElementSibling);
    }
    changedHere();
  }

  function removeImage() {
    const img = chosenImage;
    closeImagePanel(false);
    area.focus();
    const paragraph = img.parentElement;
    img.remove();
    if (paragraph !== area && paragraph.tagName === "P" && !paragraph.textContent.trim() &&
        !paragraph.querySelector("img")) {
      paragraph.remove();
    }
    ensureParagraph();
    changedHere();
  }

  area.addEventListener("click", (event) => {
    const img = event.target.closest("img");
    if (img && area.contains(img) && !img.closest(SHOWN_ONLY)) openImage(img);
  });
  panel.addEventListener("input", showImageState);
  panel.addEventListener("change", showImageState);
  panel.addEventListener("click", (event) => {
    const action = event.target.closest("button")?.dataset.image;
    if (action === "apply") applyImage();
    else if (action === "remove") removeImage();
    else if (action === "cancel") closeImagePanel();
  });
  panel.addEventListener("keydown", (event) => {
    // As in the link panel: Enter in a field inserts, not submits.
    if (event.key === "Enter" && event.target.tagName !== "BUTTON") {
      event.preventDefault();
      if (!applyImageButton.hidden) applyImage();
    } else if (event.key === "Escape") {
      event.preventDefault();
      closeImagePanel();
    }
  });

  return {
    open: openImage,
    close: closeImagePanel,
    contains: (node) => panel.contains(node),
    // A dropped picture's src as the body stores it, if it is one of the
    // body's own chart images.
    ownSrc: (src) => ownImages.get(src),
  };
}
