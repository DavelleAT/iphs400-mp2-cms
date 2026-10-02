import {TABLE_SCROLL, buildTable, caretIn, element, tableWrapper} from "./editor-dom.js";

// Tables in the Editor's body (static/editor.js): edited in place, the
// first row always the header (spec #14, T15). Each change lays the table
// out again from its cells' contents.

// A new table's size: its header row and two more, three columns across.
const NEW_TABLE = {rows: 3, columns: 3};

// `ed` is the Editor the tables are in: its body, its table controls, and
// the helpers it shares.
export function tables(ed) {
  const {area, closest, placeBlocks, changedHere, showState} = ed;

  function insertTable() {
    if (closest("table")) return;
    const rows = Array.from({length: NEW_TABLE.rows},
                            () => Array.from({length: NEW_TABLE.columns}, () => []));
    const table = buildTable(rows);
    placeBlocks([tableWrapper(table)]);
    caretIn(table.rows[0].cells[0]);
    changedHere();
  }

  ed.tableTools.addEventListener("click", (event) => {
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

  return {insert: insertTable};
}
