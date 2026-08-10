(() => {
  const grid = document.querySelector("#bias-grid");
  if (!grid) return;

  const cards = Array.from(grid.querySelectorAll("[data-bias-card]"));
  const search = document.querySelector("#search");
  const importance = document.querySelector("#importance-filter");
  const evidence = document.querySelector("#evidence-filter");
  const sort = document.querySelector("#sort-order");
  const reset = document.querySelector("#reset-filters");
  const count = document.querySelector("#result-count");
  const empty = document.querySelector("#empty-state");
  const familyButtons = Array.from(document.querySelectorAll("[data-family-filter]"));
  const evidenceRanks = { forte: 0, moderee: 1, limitee: 2, contestee: 3, a_evaluer: 4 };
  let selectedFamily = "all";

  count.setAttribute("aria-live", "polite");
  count.setAttribute("aria-atomic", "true");

  const normalize = (value) =>
    value
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLocaleLowerCase("fr");

  const apply = () => {
    const query = normalize(search.value.trim());
    const minimumImportance = Number.parseInt(importance.value, 10);
    const selectedEvidence = evidence.value;

    const ordered = [...cards].sort((a, b) => {
      if (sort.value === "alphabetical") {
        return a.dataset.name.localeCompare(b.dataset.name, "fr");
      }
      if (sort.value === "evidence") {
        const rank = evidenceRanks[a.dataset.evidence] - evidenceRanks[b.dataset.evidence];
        if (rank !== 0) return rank;
      }
      const importanceDifference = Number(b.dataset.importance) - Number(a.dataset.importance);
      if (importanceDifference !== 0) return importanceDifference;
      return a.dataset.name.localeCompare(b.dataset.name, "fr");
    });

    ordered.forEach((card) => grid.appendChild(card));

    let visible = 0;
    cards.forEach((card) => {
      const matchesSearch = !query || normalize(card.dataset.search).includes(query);
      const matchesFamily = selectedFamily === "all" || card.dataset.family === selectedFamily;
      const matchesImportance = Number(card.dataset.importance) >= minimumImportance;
      const matchesEvidence = selectedEvidence === "all" || card.dataset.evidence === selectedEvidence;
      const show = matchesSearch && matchesFamily && matchesImportance && matchesEvidence;
      card.hidden = !show;
      if (show) visible += 1;
    });

    count.textContent = String(visible);
    empty.hidden = visible !== 0;
  };

  [search, importance, evidence, sort].forEach((control) => {
    control.addEventListener(control === search ? "input" : "change", apply);
  });

  familyButtons.forEach((button) => {
    button.addEventListener("click", () => {
      selectedFamily = button.dataset.familyFilter;
      familyButtons.forEach((candidate) => {
        const active = candidate === button;
        candidate.classList.toggle("is-active", active);
        candidate.setAttribute("aria-pressed", String(active));
      });
      apply();
    });
  });

  reset.addEventListener("click", () => {
    search.value = "";
    importance.value = "0";
    evidence.value = "all";
    sort.value = "importance";
    selectedFamily = "all";
    familyButtons.forEach((button) => {
      const active = button.dataset.familyFilter === "all";
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    apply();
    search.focus();
  });

  apply();
})();
