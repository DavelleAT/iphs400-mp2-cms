// Site search (spec #22), at search.js in the site's root. search.html lists
// every published item, which is what a visitor without JavaScript sees.
// With it, this reads ?q=, searches search-index.json (published items
// only, written by `cms publish`), and lists the matches instead. Vanilla,
// no build step (ADR-002); every bit of text goes in through textContent.

// Text as search compares it: accents and case folded away, so "resume"
// finds "Résumé" and the other way round.
function folded(text) {
  return String(text).normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}

// The items whose title or summary has every word of `query`, the ones with
// more of the words in their title first, and otherwise in index order.
function searchItems(items, query) {
  const words = folded(query).split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  return items
    .map((item, order) => {
      const title = folded(item.title), summary = folded(item.summary);
      const found = words.every(word => title.includes(word) || summary.includes(word));
      return {item, order, found, inTitle: words.filter(word => title.includes(word)).length};
    })
    .filter(entry => entry.found)
    .sort((a, b) => b.inTitle - a.inTitle || a.order - b.order)
    .map(entry => entry.item);
}

if (typeof module === "object") module.exports = {folded, searchItems};

if (typeof document === "object") {
  (async () => {
    const query = new URLSearchParams(location.search).get("q") || "";
    for (const input of document.querySelectorAll('input[name="q"]')) input.value = query;
    if (!query.trim()) return;  // the full list stands

    const list = document.querySelector(".list-search"), status = document.querySelector(".search-status");
    let index;
    try {
      const response = await fetch("search-index.json");
      if (!response.ok) throw new Error(response.statusText);
      index = await response.json();
    } catch {
      status.textContent = "Search isn't working right now, so every published item is listed below.";
      return;
    }
    const found = searchItems(index, query);
    list.replaceChildren(...found.map(item => {
      const row = document.createElement("li"), link = document.createElement("a");
      const facts = document.createElement("span"), date = document.createElement("time");
      link.href = item.path;
      link.textContent = item.title;
      facts.className = "text-label text-mono";
      date.dateTime = item.date;
      date.textContent = item.date;
      facts.append(date, ` · ${item.kind}`);
      row.append(link, facts);
      if (item.summary) {
        const summary = document.createElement("p");
        summary.textContent = item.summary;
        row.append(summary);
      }
      return row;
    }));
    const quoted = `“${query.trim()}”`;
    status.textContent = found.length === 0 ? `Nothing published matches ${quoted}.`
      : found.length === 1 ? `1 result for ${quoted}.`
      : `${found.length} results for ${quoted}, title matches first.`;
    document.title = `Search: ${query.trim()} · ${document.title.split(" · ").pop()}`;
  })();
}
