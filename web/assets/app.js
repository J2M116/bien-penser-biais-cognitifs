(() => {
  const grid = document.querySelector("#bias-grid");
  if (!grid) return;

  const cards = Array.from(grid.querySelectorAll("[data-bias-card]"));
  const search = document.querySelector("#search");
  const importance = document.querySelector("#importance-filter");
  const evidence = document.querySelector("#evidence-filter");
  const review = document.querySelector("#review-filter");
  const sort = document.querySelector("#sort-order");
  const reset = document.querySelector("#reset-filters");
  const count = document.querySelector("#result-count");
  const empty = document.querySelector("#empty-state");
  const familyButtons = Array.from(document.querySelectorAll("[data-family-filter]"));
  const personalButtons = Array.from(document.querySelectorAll("[data-personal-scope]"));
  const personalStatus = document.querySelector("[data-personal-filter-status]");
  const evidenceRanks = { forte: 0, moderee: 1, limitee: 2, contestee: 3, a_evaluer: 4 };
  const reviewRanks = { en_revue: 0, non_revue: 1, revue: 2 };
  let selectedFamily = "all";
  let selectedPersonalScope = "all";

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
    const selectedReview = review.value;

    const ordered = [...cards].sort((a, b) => {
      if (sort.value === "alphabetical") {
        return a.dataset.name.localeCompare(b.dataset.name, "fr");
      }
      if (sort.value === "evidence") {
        const rank = evidenceRanks[a.dataset.evidence] - evidenceRanks[b.dataset.evidence];
        if (rank !== 0) return rank;
      }
      if (sort.value === "review") {
        const rank = reviewRanks[a.dataset.review] - reviewRanks[b.dataset.review];
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
      const matchesReview = selectedReview === "all" || card.dataset.review === selectedReview;
      const matchesPersonal = selectedPersonalScope === "all"
        || (selectedPersonalScope === "mine" && card.dataset.userRated === "true")
        || (selectedPersonalScope === "unrated" && card.dataset.userRated === "false");
      const show = matchesSearch && matchesFamily && matchesImportance && matchesEvidence
        && matchesReview && matchesPersonal;
      card.hidden = !show;
      if (show) visible += 1;
    });

    count.textContent = String(visible);
    empty.hidden = visible !== 0;
  };

  [search, importance, evidence, review, sort].forEach((control) => {
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

  const renderPersonalButtons = () => {
    personalButtons.forEach((button) => {
      const active = button.dataset.personalScope === selectedPersonalScope;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  };

  personalButtons.forEach((button) => {
    button.addEventListener("click", () => {
      selectedPersonalScope = button.dataset.personalScope;
      renderPersonalButtons();
      apply();
    });
  });

  document.addEventListener("bienpenser:personal-ratings-changed", (event) => {
    const signedIn = Boolean(event.detail?.signedIn);
    const ready = Boolean(event.detail?.ready);
    personalButtons.forEach((button) => {
      button.disabled = button.dataset.personalScope !== "all" && !ready;
    });
    if (!ready) selectedPersonalScope = "all";
    if (personalStatus) {
      personalStatus.textContent = ready
        ? "Vos notes sont chargées : choisissez les fiches notées ou celles qui restent à noter."
        : signedIn
          ? "Vos notes n’ont pas pu être chargées ; le catalogue complet reste affiché."
          : "Connectez-vous pour filtrer le catalogue selon vos notes.";
    }
    renderPersonalButtons();
    apply();
  });

  reset.addEventListener("click", () => {
    search.value = "";
    importance.value = "0";
    evidence.value = "all";
    review.value = "all";
    sort.value = "importance";
    selectedFamily = "all";
    selectedPersonalScope = "all";
    familyButtons.forEach((button) => {
      const active = button.dataset.familyFilter === "all";
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    renderPersonalButtons();
    apply();
    search.focus();
  });

  apply();
})();
