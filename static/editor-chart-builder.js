import {element, parseJson} from "./editor-dom.js";
import {spreadsheetRows} from "./editor-paste.js";

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

export function chartBuilder(previewPath, csrfToken) {
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
      Paste a range from Excel or Sheets into any cell; its top-left cell, if it names the
      categories, becomes the category axis label. Empty rows and series at the end are left out.</p>
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
  let onInsert = null;
  // Said once after a paste the grid couldn't hold all of.
  let pasteNote = "";

  function open(text, inserted) {
    const chart = text ? parseJson(text, null) : null;
    state = chart ? fromChart(chart) : blankChart();
    touched = new Set();
    showAll = Boolean(chart);
    onInsert = inserted;
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
      // Its Remove under its name, so the column is as wide as its cells.
      head.append(cell("th", [element("div", {class: "admin-chart-builder-name"}, [
        ...gridInput(`series.${column}.name`, series.name, `Series ${column + 1} name`),
        ...(many ? [gridButton("Remove", `Remove series ${column + 1}`,
                               () => removeSeries(column))] : [])])], {scope: "col"}));
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
  // The cell above the category names names them: the category axis
  // label, unless the writer has given one. One column (a series copied
  // with its name) is never category names: pasted into a series, its
  // first cell is that series' name, if it isn't a number.
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
    const oneColumn = rows.every((cells) => cells.length === 1);
    const seriesNames = oneColumn
      ? left > 0 && rows.length > 1 && Boolean(rows[0][0]) && !isValue(rows[0][0])
      : rows[0].some((text, column) => column > 0 && text && !isValue(text));
    const categoryNames = !oneColumn && rows.slice(seriesNames ? 1 : 0)
      .some((cells) => cells[0] && !isValue(cells[0]));
    if (seriesNames) top = 0;
    if (categoryNames) left = 0;
    let cut = false;
    rows.forEach((cells, down) => cells.forEach((text, across) => {
      const row = top + down;
      const column = left + across;
      if (!row && !column) {
        if (text && !state.x_label.trim()) {
          setField("x_label", text);
          dialog.querySelector("[data-field=x_label]").value = text;
          touched.add("x_label");
        }
        return;
      }
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
      const {chart, drawing} = answer;
      dialog.close();
      onInsert(chart, drawing);
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
      if (found && found.drawing) {
        // The server's drawing (app.chart_drawing), safe as it is built.
        preview.innerHTML = found.drawing;
      } else if (!preview.querySelector("figure")) {
        preview.replaceChildren(element("p", {}, ["No chart yet."]));
      }
      // The last drawing stays, faded, until the Chart is valid again, so
      // the dialog doesn't jump as the writer types.
      preview.classList.toggle("admin-chart-builder-stale", !(found && found.drawing));
      showAnswer();
    }, delay);
  }

  function ready() {
    return !pending && Boolean(answer) && !answer.errors.length && Boolean(answer.chart);
  }

  function errorShown(name) {
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
        if (!errorShown(name)) continue;
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
