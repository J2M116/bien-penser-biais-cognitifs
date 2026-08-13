import { createClient } from "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.95.0/+esm";
import { SITE_URL, SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL } from "./supabase-config.js";

const supabase = createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, {
  auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
});

const state = {
  user: null,
  profile: null,
  aggregates: new Map(),
  personal: new Map(),
  personalReady: false,
  canReview: false,
};

const authDialog = document.querySelector("#auth-dialog");
const authMessage = document.querySelector("[data-auth-message]");

const setMessage = (element, message, kind = "") => {
  if (!element) return;
  element.textContent = message;
  element.dataset.kind = kind;
};

const formatCount = (count) => {
  if (!count) return "Aucune évaluation";
  return `${count} évaluation${count > 1 ? "s" : ""}`;
};

const openAuthDialog = () => {
  if (!authDialog) return;
  if (!authDialog.open) authDialog.showModal();
};

document.querySelectorAll("[data-auth-open]").forEach((button) => {
  button.addEventListener("click", openAuthDialog);
});

document.querySelectorAll("[data-auth-tab]").forEach((button) => {
  button.addEventListener("click", () => {
    const selected = button.dataset.authTab;
    document.querySelectorAll("[data-auth-tab]").forEach((candidate) => {
      const active = candidate === button;
      candidate.classList.toggle("is-active", active);
      candidate.setAttribute("aria-selected", String(active));
    });
    document.querySelectorAll("[data-auth-form]").forEach((form) => {
      form.hidden = form.dataset.authForm !== selected;
    });
    setMessage(authMessage, "");
  });
});

const friendlyAuthError = (error) => {
  const message = error?.message || "Une erreur est survenue.";
  const translations = [
    [/invalid login credentials/i, "Adresse e-mail ou mot de passe incorrect."],
    [/user already registered/i, "Un compte existe déjà avec cette adresse."],
    [/password should be at least/i, "Le mot de passe doit contenir au moins 6 caractères."],
    [/email rate limit/i, "Trop d'e-mails ont été demandés. Réessayez un peu plus tard."],
    [/unable to validate email/i, "Cette adresse e-mail n'est pas valide."],
  ];
  return translations.find(([pattern]) => pattern.test(message))?.[1] || message;
};

document.querySelectorAll("[data-auth-form]").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector("button[type='submit']");
    const values = new FormData(form);
    submit.disabled = true;
    setMessage(authMessage, "Connexion en cours…");
    try {
      if (form.dataset.authForm === "login") {
        const { error } = await supabase.auth.signInWithPassword({
          email: String(values.get("email")).trim(),
          password: String(values.get("password")),
        });
        if (error) throw error;
        setMessage(authMessage, "Connexion réussie.", "success");
        form.reset();
      } else {
        const displayName = String(values.get("display_name")).trim();
        const { data, error } = await supabase.auth.signUp({
          email: String(values.get("email")).trim(),
          password: String(values.get("password")),
          options: {
            data: { display_name: displayName },
            emailRedirectTo: SITE_URL,
          },
        });
        if (error) throw error;
        if (data.session) {
          setMessage(authMessage, "Compte créé et connecté.", "success");
        } else {
          setMessage(authMessage, "Compte créé. Consultez votre e-mail pour confirmer votre inscription.", "success");
        }
        form.reset();
      }
    } catch (error) {
      setMessage(authMessage, friendlyAuthError(error), "error");
    } finally {
      submit.disabled = false;
    }
  });
});

document.querySelector("[data-sign-out]")?.addEventListener("click", async () => {
  await supabase.auth.signOut();
  authDialog?.close();
});

const loadProfile = async () => {
  state.profile = null;
  if (!state.user) return;
  const { data } = await supabase
    .from("profiles")
    .select("display_name")
    .eq("user_id", state.user.id)
    .maybeSingle();
  state.profile = data;
};

const loadPersonalRatings = async () => {
  state.personal.clear();
  state.personalReady = false;
  if (!state.user) return;
  const { data, error } = await supabase.from("ratings").select("bias_id, score");
  if (error) return;
  data.forEach((rating) => state.personal.set(rating.bias_id, Number(rating.score)));
  state.personalReady = true;
};

const loadReviewerAccess = async () => {
  state.canReview = false;
  if (!state.user) return;
  const { data, error } = await supabase
    .from("reviewer_access")
    .select("user_id")
    .eq("user_id", state.user.id)
    .maybeSingle();
  if (!error && data?.user_id === state.user.id) state.canReview = true;
};

const publishPersonalRatingState = () => {
  const signedIn = Boolean(state.user);
  const ready = signedIn && state.personalReady;
  document.querySelectorAll("[data-bias-card][data-bias-id]").forEach((card) => {
    card.dataset.userRated = ready ? String(state.personal.has(card.dataset.biasId)) : "unknown";
  });
  document.dispatchEvent(new CustomEvent("bienpenser:personal-ratings-changed", {
    detail: { signedIn, ready },
  }));
};

const renderAuth = () => {
  const signedIn = Boolean(state.user);
  document.querySelectorAll("[data-account-label]").forEach((label) => {
    label.textContent = signedIn ? state.profile?.display_name || "Mon compte" : "Se connecter";
  });
  document.querySelectorAll(".account-button").forEach((button) => {
    button.classList.toggle("is-connected", signedIn);
  });
  document.querySelector("[data-auth-anonymous]")?.toggleAttribute("hidden", signedIn);
  document.querySelector("[data-auth-profile]")?.toggleAttribute("hidden", !signedIn);
  const profileName = document.querySelector("[data-profile-name]");
  if (profileName) profileName.textContent = state.profile?.display_name || "membre";
  document.querySelectorAll("[data-rating-signed-out]").forEach((panel) => {
    panel.hidden = signedIn;
  });
  document.querySelectorAll("[data-rating-form]").forEach((form) => {
    form.hidden = !signedIn;
  });
};

const renderReviewerAccess = () => {
  document.querySelectorAll("[data-reviewer-only]").forEach((element) => {
    element.hidden = !state.canReview;
  });
  document.querySelectorAll("[data-reviewer-locked]").forEach((element) => {
    element.hidden = state.canReview;
  });
  document.querySelectorAll("[data-reviewer-badge]").forEach((element) => {
    element.hidden = !state.canReview;
  });
  document.querySelectorAll("[data-reviewer-card]").forEach((card) => {
    const link = card.querySelector("[data-card-primary-action]");
    const label = card.querySelector("[data-card-action-label]");
    if (!link || !label) return;
    if (state.canReview && link.dataset.reviewerHref) {
      link.setAttribute("href", link.dataset.reviewerHref);
      link.setAttribute("aria-label", link.dataset.reviewerAriaLabel);
      link.setAttribute("target", "_blank");
      link.setAttribute("rel", "noreferrer");
      label.textContent = "Revoir la fiche";
    } else {
      link.setAttribute("href", link.dataset.publicHref);
      link.setAttribute("aria-label", link.dataset.publicAriaLabel);
      link.removeAttribute("target");
      link.removeAttribute("rel");
      label.textContent = "Lire la fiche";
    }
  });
};

const loadAggregates = async () => {
  const { data, error } = await supabase
    .from("bias_score_summaries")
    .select("bias_id, average_score, median_score, ratings_count");
  if (error) return;
  state.aggregates.clear();
  data.forEach((row) => {
    state.aggregates.set(row.bias_id, {
      average: Number(row.average_score),
      median: Number(row.median_score),
      count: Number(row.ratings_count),
    });
  });
};

const renderCommunityScores = () => {
  document.querySelectorAll("[data-community-score]").forEach((element) => {
    const score = state.aggregates.get(element.dataset.communityScore);
    const value = element.querySelector("[data-score-value]");
    const count = element.querySelector("[data-score-count]");
    value.textContent = score ? Math.round(score.average) : "—";
    count.textContent = score ? formatCount(score.count) : "Aucune évaluation";
    element.classList.toggle("has-score", Boolean(score));
    element.classList.toggle("is-provisional", Boolean(score && score.count < 3));
    if (score && score.count < 3) count.textContent += " · provisoire";
  });
};

const renderRatingWidgets = () => {
  document.querySelectorAll("[data-rating-widget]").forEach((widget) => {
    const biasId = widget.dataset.ratingWidget;
    const form = widget.querySelector("[data-rating-form]");
    const input = form?.querySelector("input[type='range']");
    const output = form?.querySelector("[data-rating-output]");
    const deleteButton = form?.querySelector("[data-rating-delete]");
    const personalScore = state.personal.get(biasId);
    if (!input || !output || !deleteButton) return;
    input.value = personalScore || 50;
    output.textContent = input.value;
    deleteButton.hidden = !personalScore;
  });
};

document.querySelectorAll("[data-rating-form]").forEach((form) => {
  const widget = form.closest("[data-rating-widget]");
  const input = form.querySelector("input[type='range']");
  const output = form.querySelector("[data-rating-output]");
  const message = form.querySelector("[data-rating-message]");
  input.addEventListener("input", () => {
    output.textContent = input.value;
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.user) return openAuthDialog();
    const submit = form.querySelector("button[type='submit']");
    submit.disabled = true;
    setMessage(message, "Enregistrement…");
    const rating = {
      user_id: state.user.id,
      bias_id: widget.dataset.ratingWidget,
      score: Number(input.value),
    };
    const { error } = await supabase.from("ratings").upsert(rating, { onConflict: "user_id,bias_id" });
    if (error) {
      setMessage(message, error.message, "error");
    } else {
      state.personal.set(rating.bias_id, rating.score);
      publishPersonalRatingState();
      setMessage(message, "Votre note est enregistrée.", "success");
      await loadAggregates();
      renderCommunityScores();
      renderRatingWidgets();
      renderLeaderboard();
    }
    submit.disabled = false;
  });
  form.querySelector("[data-rating-delete]")?.addEventListener("click", async () => {
    if (!state.user) return;
    const biasId = widget.dataset.ratingWidget;
    const { error } = await supabase
      .from("ratings")
      .delete()
      .eq("user_id", state.user.id)
      .eq("bias_id", biasId);
    if (error) return setMessage(message, error.message, "error");
    state.personal.delete(biasId);
    publishPersonalRatingState();
    setMessage(message, "Votre note a été supprimée.", "success");
    await loadAggregates();
    renderCommunityScores();
    renderRatingWidgets();
    renderLeaderboard();
  });
});

const leaderboardRows = Array.from(document.querySelectorAll("[data-leaderboard-row]"));

const renderLeaderboard = () => {
  if (!leaderboardRows.length) return;
  const query = (document.querySelector("[data-leaderboard-search]")?.value || "").trim().toLocaleLowerCase("fr");
  const family = document.querySelector("[data-leaderboard-family]")?.value || "all";
  const scope = document.querySelector("[data-leaderboard-scope]")?.value || "all";
  const tbody = leaderboardRows[0].parentElement;
  const ordered = [...leaderboardRows].sort((left, right) => {
    const a = state.aggregates.get(left.dataset.biasId);
    const b = state.aggregates.get(right.dataset.biasId);
    if (!a && !b) return left.dataset.name.localeCompare(right.dataset.name, "fr");
    if (!a) return 1;
    if (!b) return -1;
    return b.average - a.average || b.count - a.count || left.dataset.name.localeCompare(right.dataset.name, "fr");
  });
  let rank = 0;
  let total = 0;
  ordered.forEach((row) => {
    const aggregate = state.aggregates.get(row.dataset.biasId);
    const personal = state.personal.get(row.dataset.biasId);
    const show = (!query || row.dataset.name.includes(query))
      && (family === "all" || row.dataset.family === family)
      && (scope === "all" || (scope === "rated" && aggregate) || (scope === "mine" && personal));
    row.hidden = !show;
    if (show) rank += 1;
    row.querySelector("[data-rank]").textContent = aggregate ? String(rank) : "—";
    row.querySelector("[data-score]").textContent = aggregate ? aggregate.average.toFixed(1).replace(".0", "") : "—";
    row.querySelector("[data-median]").textContent = aggregate ? aggregate.median.toFixed(1).replace(".0", "") : "—";
    row.querySelector("[data-count]").textContent = aggregate ? String(aggregate.count) : "0";
    row.querySelector("[data-personal]").textContent = personal ? `${personal}/100` : "—";
    row.classList.toggle("is-provisional", Boolean(aggregate && aggregate.count < 3));
    if (aggregate) total += aggregate.count;
    tbody.appendChild(row);
  });
  const totalElement = document.querySelector("[data-ratings-total]");
  if (totalElement) totalElement.textContent = String(total);
};

document.querySelectorAll("[data-leaderboard-search], [data-leaderboard-family], [data-leaderboard-scope]").forEach((control) => {
  control.addEventListener(control.matches("input") ? "input" : "change", renderLeaderboard);
});

const synchronize = async (user) => {
  state.user = user;
  await Promise.all([loadProfile(), loadPersonalRatings(), loadAggregates(), loadReviewerAccess()]);
  renderAuth();
  renderReviewerAccess();
  renderCommunityScores();
  renderRatingWidgets();
  renderLeaderboard();
  publishPersonalRatingState();
};

const { data: { session } } = await supabase.auth.getSession();
await synchronize(session?.user || null);

supabase.auth.onAuthStateChange((_event, nextSession) => {
  window.setTimeout(() => synchronize(nextSession?.user || null), 0);
});
