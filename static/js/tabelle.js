// Verhalten für templates/macros/tabelle.html: Suche, Sortierung, Leerzeile,
// klickbare Zeilen (tr[data-href]) und "Alle auswählen".
(function () {
  "use strict";

  const INTERAKTIV = "a, button, input, label, select, textarea";

  function initTabelle(wrapper) {
    const table = wrapper.querySelector("table");
    const tbody = table.tBodies[0];
    const suche = wrapper.querySelector(".tabelle-suche");
    const alleBtn = wrapper.querySelector(".tabelle-alle");
    const spaltenAnzahl = table.tHead.rows[0].cells.length;

    const datenZeilen = () =>
      Array.from(tbody.rows).filter(r => !r.classList.contains("tabelle-leer"));

    // ------------------------------------------------
    // Leer- bzw. Kein-Treffer-Zeile
    // ------------------------------------------------
    function aktualisiereLeerzeile() {
      const zeilen = datenZeilen();
      const sichtbar = zeilen.filter(r => !r.hidden).length;
      let leer = tbody.querySelector("tr.tabelle-leer");

      if (sichtbar > 0) {
        if (leer) leer.remove();
        return;
      }
      if (!leer) {
        leer = tbody.insertRow();
        leer.className = "tabelle-leer";
        const td = leer.insertCell();
        td.colSpan = spaltenAnzahl;
        td.className = "text-center text-muted py-4";
      }
      leer.cells[0].textContent = zeilen.length ? "Keine Treffer." : wrapper.dataset.leer;
    }

    // ------------------------------------------------
    // Suche
    // ------------------------------------------------
    if (suche) {
      suche.addEventListener("input", () => {
        const begriff = suche.value.trim().toLowerCase();
        datenZeilen().forEach(r => {
          r.hidden = begriff !== "" && !r.textContent.toLowerCase().includes(begriff);
        });
        aktualisiereLeerzeile();
        aktualisiereAlleBtn();
      });
    }

    // ------------------------------------------------
    // Sortierung
    // ------------------------------------------------
    function sortWert(zeile, index) {
      const zelle = zeile.cells[index];
      if (!zelle) return "";
      return zelle.dataset.wert !== undefined ? zelle.dataset.wert : zelle.textContent.trim();
    }

    function vergleiche(a, b) {
      const na = Number(a), nb = Number(b);
      if (a !== "" && b !== "" && !isNaN(na) && !isNaN(nb)) return na - nb;
      return a.localeCompare(b, "de", { numeric: true, sensitivity: "base" });
    }

    function sortiere(th) {
      const aufsteigend = th.getAttribute("aria-sort") !== "ascending";
      table.tHead.querySelectorAll("th[data-sort]").forEach(t => t.setAttribute("aria-sort", "none"));
      th.setAttribute("aria-sort", aufsteigend ? "ascending" : "descending");

      const index = th.cellIndex;
      const richtung = aufsteigend ? 1 : -1;
      datenZeilen()
        .map((zeile, pos) => ({ zeile, pos, wert: sortWert(zeile, index) }))
        .sort((x, y) => richtung * vergleiche(x.wert, y.wert) || x.pos - y.pos)
        .forEach(({ zeile }) => tbody.appendChild(zeile));
      aktualisiereLeerzeile();
    }

    table.tHead.querySelectorAll("th[data-sort]").forEach(th => {
      th.addEventListener("click", () => sortiere(th));
      th.addEventListener("keydown", e => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          sortiere(th);
        }
      });
    });

    // ------------------------------------------------
    // Klickbare Zeilen
    // ------------------------------------------------
    tbody.addEventListener("click", e => {
      const zeile = e.target.closest("tr[data-href]");
      if (!zeile || e.target.closest(INTERAKTIV)) return;
      window.location.href = zeile.dataset.href;
    });

    // ------------------------------------------------
    // Alle auswählen / abwählen
    // ------------------------------------------------
    const waehlbar = () =>
      datenZeilen()
        .filter(r => !r.hidden)
        .flatMap(r => Array.from(r.querySelectorAll("input.tabelle-auswahl:not(:disabled)")));

    function aktualisiereAlleBtn() {
      if (!alleBtn) return;
      const boxen = waehlbar();
      const alleAn = boxen.length > 0 && boxen.every(b => b.checked);
      alleBtn.textContent = alleAn ? "Alle abwählen" : "Alle auswählen";
      alleBtn.disabled = boxen.length === 0;
    }

    if (alleBtn) {
      alleBtn.addEventListener("click", () => {
        const boxen = waehlbar();
        const ziel = !boxen.every(b => b.checked);
        boxen.forEach(b => {
          if (b.checked !== ziel) {
            b.checked = ziel;
            b.dispatchEvent(new Event("change", { bubbles: true }));
          }
        });
        aktualisiereAlleBtn();
      });
      tbody.addEventListener("change", aktualisiereAlleBtn);
      aktualisiereAlleBtn();
    }

    aktualisiereLeerzeile();
  }

  function initAlle() {
    document.querySelectorAll("[data-tabelle]").forEach(initTabelle);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAlle);
  } else {
    initAlle();
  }
})();
