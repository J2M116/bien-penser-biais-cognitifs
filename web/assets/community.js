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
  personalExamples: new Map(),
  personalExamplesReady: false,
  personalExamplesError: false,
  communityExamples: new Map(),
  communityExamplesReady: false,
  communityExamplesError: false,
  personalHeartIds: new Set(),
  personalHeartsReady: false,
  personalHeartsError: false,
  canReview: false,
};

const authDialog = document.querySelector("#auth-dialog");
const authMessage = document.querySelector("[data-auth-message]");
const exampleSlotDefaults = new WeakMap();
const cardSearchDefaults = new WeakMap();
let syncEpoch = 0;

const currentUserId = () => state.user?.id || null;
const captureSyncContext = () => ({ epoch: syncEpoch, userId: currentUserId() });
const isCurrentSyncContext = (context) => (
  context.epoch === syncEpoch && context.userId === currentUserId()
);

document.querySelectorAll("[data-example-slot]").forEach((slot) => {
  const label = slot.querySelector("[data-example-label]");
  const text = slot.querySelector("[data-example-text]");
  if (!label || !text) return;
  exampleSlotDefaults.set(slot, {
    label: label.textContent,
    nodes: Array.from(text.childNodes).map((node) => node.cloneNode(true)),
  });
  const card = slot.closest("[data-bias-card]");
  if (card && !cardSearchDefaults.has(card)) cardSearchDefaults.set(card, card.dataset.search);
});

const setMessage = (element, message, kind = "") => {
  if (!element) return;
  element.textContent = message;
  element.dataset.kind = kind;
};

const formatCount = (count) => {
  if (!count) return "Aucune évaluation";
  return `${count} évaluation${count > 1 ? "s" : ""}`;
};

const formatHearts = (count) => `${count} cœur${count > 1 ? "s" : ""}`;

const formatExampleDate = (value) => new Intl.DateTimeFormat("fr-FR", {
  day: "numeric",
  month: "long",
  year: "numeric",
}).format(new Date(value));

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

const loadProfile = async (context = captureSyncContext()) => {
  state.profile = null;
  if (!context.userId) return;
  const { data } = await supabase
    .from("profiles")
    .select("display_name")
    .eq("user_id", context.userId)
    .maybeSingle();
  if (!isCurrentSyncContext(context)) return;
  state.profile = data;
};

const loadPersonalRatings = async (context = captureSyncContext()) => {
  state.personal.clear();
  state.personalReady = false;
  if (!context.userId) return;
  const { data, error } = await supabase
    .from("ratings")
    .select("bias_id, score")
    .eq("user_id", context.userId);
  if (!isCurrentSyncContext(context)) return;
  if (error) return;
  data.forEach((rating) => state.personal.set(rating.bias_id, Number(rating.score)));
  state.personalReady = true;
};

const visibleBiasIds = () => Array.from(new Set(
  Array.from(document.querySelectorAll("[data-example-slot][data-bias-id]"))
    .map((slot) => slot.dataset.biasId),
));

const loadPersonalExamples = async (context = captureSyncContext()) => {
  state.personalExamples.clear();
  state.personalExamplesReady = false;
  state.personalExamplesError = false;
  if (!context.userId) return;
  const biasIds = visibleBiasIds();
  if (!biasIds.length) {
    state.personalExamplesReady = true;
    return;
  }
  const { data, error } = await supabase
    .from("bias_examples")
    .select("id, bias_id, example_text")
    .eq("user_id", context.userId)
    .in("bias_id", biasIds);
  if (!isCurrentSyncContext(context)) return;
  if (error) {
    state.personalExamplesError = true;
    return;
  }
  data.forEach((example) => state.personalExamples.set(example.bias_id, example));
  state.personalExamplesReady = true;
};

const loadCommunityExamples = async (context = captureSyncContext()) => {
  state.communityExamples.clear();
  state.communityExamplesReady = false;
  state.communityExamplesError = false;
  const galleries = Array.from(document.querySelectorAll("[data-example-gallery][data-bias-id]"));
  if (!galleries.length) {
    state.communityExamplesReady = true;
    return;
  }
  const biasIds = galleries.map((gallery) => gallery.dataset.biasId);
  const { data, error } = await supabase
    .from("bias_example_summaries")
    .select("example_id, bias_id, example_text, heart_count, created_at, updated_at")
    .in("bias_id", biasIds)
    .order("heart_count", { ascending: false })
    .order("created_at", { ascending: true });
  if (!isCurrentSyncContext(context)) return;
  if (error) {
    state.communityExamplesError = true;
    return;
  }
  biasIds.forEach((biasId) => state.communityExamples.set(biasId, []));
  data.forEach((example) => {
    state.communityExamples.get(example.bias_id)?.push({
      ...example,
      heart_count: Number(example.heart_count),
    });
  });
  state.communityExamplesReady = true;
};

const loadPersonalHearts = async (context = captureSyncContext()) => {
  state.personalHeartIds.clear();
  state.personalHeartsReady = false;
  state.personalHeartsError = false;
  if (!context.userId) return;
  const exampleIds = Array.from(state.communityExamples.values())
    .flat()
    .map((example) => example.example_id);
  if (!exampleIds.length) {
    state.personalHeartsReady = true;
    return;
  }
  const { data, error } = await supabase
    .from("bias_example_hearts")
    .select("example_id")
    .eq("user_id", context.userId)
    .in("example_id", exampleIds);
  if (!isCurrentSyncContext(context)) return;
  if (error) {
    state.personalHeartsError = true;
    return;
  }
  data.forEach((heart) => state.personalHeartIds.add(heart.example_id));
  state.personalHeartsReady = true;
};

const loadReviewerAccess = async (context = captureSyncContext()) => {
  state.canReview = false;
  if (!context.userId) return;
  const { data, error } = await supabase
    .from("reviewer_access")
    .select("user_id")
    .eq("user_id", context.userId)
    .maybeSingle();
  if (!isCurrentSyncContext(context)) return;
  if (!error && data?.user_id === context.userId) state.canReview = true;
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

const renderPersonalExamples = () => {
  document.querySelectorAll("[data-example-slot][data-bias-id]").forEach((slot) => {
    const defaults = exampleSlotDefaults.get(slot);
    const label = slot.querySelector("[data-example-label]");
    const text = slot.querySelector("[data-example-text]");
    if (!defaults || !label || !text) return;
    const personal = state.user && state.personalExamplesReady
      ? state.personalExamples.get(slot.dataset.biasId)
      : null;
    if (personal) {
      label.textContent = "Votre exemple";
      text.textContent = personal.example_text;
    } else {
      label.textContent = defaults.label;
      text.replaceChildren(...defaults.nodes.map((node) => node.cloneNode(true)));
    }
    const card = slot.closest("[data-bias-card]");
    if (card) {
      const standardSearch = cardSearchDefaults.get(card) || card.dataset.search;
      card.dataset.search = personal
        ? `${standardSearch} ${personal.example_text.toLocaleLowerCase("fr")}`
        : standardSearch;
    }
  });
  document.dispatchEvent(new CustomEvent("bienpenser:personal-examples-changed"));
};

const renderPersonalExampleEditors = () => {
  const signedIn = Boolean(state.user);
  document.querySelectorAll("[data-example-editor][data-bias-id]").forEach((editor) => {
    const signedOut = editor.querySelector("[data-example-signed-out]");
    const loading = editor.querySelector("[data-example-loading]");
    const form = editor.querySelector("[data-example-form]");
    const textarea = form?.querySelector("textarea[name='example_text']");
    const counter = form?.querySelector("[data-example-counter]");
    const saveButton = form?.querySelector("[data-example-save]");
    const deleteButton = form?.querySelector("[data-example-delete]");
    signedOut?.toggleAttribute("hidden", signedIn);
    if (loading) {
      loading.hidden = !signedIn || state.personalExamplesReady;
      loading.textContent = state.personalExamplesError
        ? "Votre exemple n’a pas pu être chargé. Réessayez après avoir rechargé la page."
        : "Chargement de votre exemple…";
    }
    if (!form || !textarea || !counter || !saveButton || !deleteButton) return;
    form.hidden = !signedIn || !state.personalExamplesReady;
    if (form.hidden) return;
    saveButton.disabled = false;
    deleteButton.disabled = false;
    const personal = state.personalExamples.get(editor.dataset.biasId);
    textarea.value = personal?.example_text || "";
    counter.textContent = `${textarea.value.length}/600`;
    saveButton.textContent = personal ? "Enregistrer les modifications" : "Ajouter mon exemple";
    deleteButton.hidden = !personal;
  });
};

const renderCommunityExamples = () => {
  document.querySelectorAll("[data-example-gallery][data-bias-id]").forEach((gallery) => {
    const list = gallery.querySelector("[data-examples-list]");
    const status = gallery.querySelector("[data-examples-status]");
    const retry = gallery.querySelector("[data-examples-retry]");
    const more = gallery.querySelector("[data-examples-more]");
    const total = gallery.querySelector("[data-examples-total]");
    const totalLabel = gallery.querySelector("[data-examples-total-label]");
    if (!list || !status || !retry || !more || !total || !totalLabel) return;
    list.replaceChildren();
    list.setAttribute("aria-busy", String(!state.communityExamplesReady));
    retry.hidden = !state.communityExamplesError
      && !(Boolean(state.user) && state.personalHeartsError);
    status.dataset.kind = state.communityExamplesError ? "error" : "";

    if (!state.communityExamplesReady) {
      status.textContent = state.communityExamplesError
        ? "Les exemples partagés n’ont pas pu être chargés."
        : "Chargement des exemples partagés…";
      total.textContent = "0";
      totalLabel.textContent = "exemple partagé";
      more.hidden = true;
      return;
    }

    const examples = state.communityExamples.get(gallery.dataset.biasId) || [];
    total.textContent = String(examples.length);
    totalLabel.textContent = examples.length > 1 ? "exemples partagés" : "exemple partagé";
    status.textContent = examples.length
      ? state.personalHeartsError
        ? "Les compteurs sont visibles, mais le vote est temporairement indisponible."
        : ""
      : "Aucun exemple partagé pour l’instant. Soyez le premier à en ajouter un.";
    status.dataset.kind = state.personalHeartsError ? "error" : "";

    const visibleCount = Number.parseInt(gallery.dataset.visibleCount || "12", 10);
    examples.slice(0, visibleCount).forEach((example) => {
      const article = document.createElement("article");
      article.className = "community-example-card";
      article.dataset.exampleId = example.example_id;

      const meta = document.createElement("div");
      meta.className = "community-example-meta";
      const shared = document.createElement("span");
      shared.textContent = "Exemple partagé";
      meta.appendChild(shared);
      const personal = state.personalExamples.get(gallery.dataset.biasId);
      if (state.user && personal?.id === example.example_id) {
        const own = document.createElement("strong");
        own.textContent = "Votre exemple";
        meta.appendChild(own);
        article.classList.add("is-personal");
      }

      const text = document.createElement("p");
      text.className = "community-example-text";
      text.textContent = example.example_text;

      const footer = document.createElement("div");
      footer.className = "community-example-footer";
      const time = document.createElement("time");
      time.dateTime = example.created_at;
      time.textContent = formatExampleDate(example.created_at);

      const liked = state.personalHeartIds.has(example.example_id);
      const heart = document.createElement("button");
      heart.className = `example-heart${liked ? " is-liked" : ""}`;
      heart.type = "button";
      heart.dataset.exampleHeart = example.example_id;
      heart.setAttribute("aria-pressed", String(liked));
      heart.setAttribute(
        "aria-label",
        `${liked ? "Retirer votre cœur" : "Attribuer un cœur"} — ${formatHearts(example.heart_count)}`,
      );
      heart.disabled = Boolean(state.user) && !state.personalHeartsReady;
      const symbol = document.createElement("span");
      symbol.setAttribute("aria-hidden", "true");
      symbol.textContent = liked ? "♥" : "♡";
      const count = document.createElement("span");
      count.textContent = String(example.heart_count);
      heart.append(symbol, count);
      heart.addEventListener("click", () => toggleExampleHeart(example.example_id, gallery));

      footer.append(time, heart);
      article.append(meta, text, footer);
      list.appendChild(article);
    });
    more.hidden = visibleCount >= examples.length;
  });
};

const loadAggregates = async (context = captureSyncContext()) => {
  const { data, error } = await supabase
    .from("bias_score_summaries")
    .select("bias_id, average_score, median_score, ratings_count");
  if (!isCurrentSyncContext(context)) return;
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
    const submitButton = form?.querySelector("button[type='submit']");
    const personalScore = state.personal.get(biasId);
    if (!input || !output || !deleteButton || !submitButton) return;
    submitButton.disabled = false;
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
    const context = captureSyncContext();
    const submit = form.querySelector("button[type='submit']");
    submit.disabled = true;
    setMessage(message, "Enregistrement…");
    const rating = {
      user_id: state.user.id,
      bias_id: widget.dataset.ratingWidget,
      score: Number(input.value),
    };
    const { error } = await supabase.from("ratings").upsert(rating, { onConflict: "user_id,bias_id" });
    if (!isCurrentSyncContext(context)) return;
    if (error) {
      setMessage(message, error.message, "error");
    } else {
      state.personal.set(rating.bias_id, rating.score);
      publishPersonalRatingState();
      setMessage(message, "Votre note est enregistrée.", "success");
      await loadAggregates(context);
      if (!isCurrentSyncContext(context)) return;
      renderCommunityScores();
      renderRatingWidgets();
      renderLeaderboard();
    }
    submit.disabled = false;
  });
  form.querySelector("[data-rating-delete]")?.addEventListener("click", async () => {
    if (!state.user) return;
    const context = captureSyncContext();
    const biasId = widget.dataset.ratingWidget;
    const { error } = await supabase
      .from("ratings")
      .delete()
      .eq("user_id", state.user.id)
      .eq("bias_id", biasId);
    if (!isCurrentSyncContext(context)) return;
    if (error) return setMessage(message, error.message, "error");
    state.personal.delete(biasId);
    publishPersonalRatingState();
    setMessage(message, "Votre note a été supprimée.", "success");
    await loadAggregates(context);
    if (!isCurrentSyncContext(context)) return;
    renderCommunityScores();
    renderRatingWidgets();
    renderLeaderboard();
  });
});

document.querySelectorAll("[data-example-form]").forEach((form) => {
  const editor = form.closest("[data-example-editor]");
  const textarea = form.querySelector("textarea[name='example_text']");
  const counter = form.querySelector("[data-example-counter]");
  const message = form.querySelector("[data-example-message]");
  const saveButton = form.querySelector("[data-example-save]");
  const deleteButton = form.querySelector("[data-example-delete]");
  textarea.addEventListener("input", () => {
    counter.textContent = `${textarea.value.length}/600`;
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.user) return openAuthDialog();
    if (!state.personalExamplesReady) {
      return setMessage(message, "Votre exemple doit d’abord être chargé.", "error");
    }
    const context = captureSyncContext();
    const biasId = editor.dataset.biasId;
    const exampleText = textarea.value.trim();
    if (exampleText.length < 10) {
      return setMessage(
        message,
        "Votre exemple doit contenir au moins 10 caractères hors espaces.",
        "error",
      );
    }
    saveButton.disabled = true;
    deleteButton.disabled = true;
    setMessage(message, "Enregistrement…");
    const current = state.personalExamples.get(biasId);
    const request = current
      ? supabase
        .from("bias_examples")
        .update({ example_text: exampleText })
        .eq("user_id", context.userId)
        .eq("bias_id", biasId)
      : supabase
        .from("bias_examples")
        .insert({ user_id: context.userId, bias_id: biasId, example_text: exampleText });
    const { data, error } = await request
      .select("id, bias_id, example_text")
      .single();
    if (!isCurrentSyncContext(context)) return;
    if (error) {
      setMessage(message, error.message, "error");
    } else {
      state.personalExamples.set(biasId, data);
      renderPersonalExamples();
      renderPersonalExampleEditors();
      await loadCommunityExamples(context);
      if (!isCurrentSyncContext(context)) return;
      renderCommunityExamples();
      setMessage(message, current ? "Votre exemple a été modifié." : "Votre exemple a été ajouté.", "success");
    }
    saveButton.disabled = false;
    deleteButton.disabled = false;
  });
  deleteButton.addEventListener("click", async () => {
    if (!state.user || !state.personalExamplesReady) return;
    const context = captureSyncContext();
    const biasId = editor.dataset.biasId;
    const current = state.personalExamples.get(biasId);
    if (!current || !window.confirm("Supprimer votre exemple public pour ce biais ?")) return;
    saveButton.disabled = true;
    deleteButton.disabled = true;
    setMessage(message, "Suppression…");
    const { error } = await supabase
      .from("bias_examples")
      .delete()
      .eq("user_id", context.userId)
      .eq("bias_id", biasId);
    if (!isCurrentSyncContext(context)) return;
    if (error) {
      setMessage(message, error.message, "error");
      saveButton.disabled = false;
      deleteButton.disabled = false;
      return;
    }
    state.personalExamples.delete(biasId);
    state.personalHeartIds.delete(current.id);
    renderPersonalExamples();
    renderPersonalExampleEditors();
    await loadCommunityExamples(context);
    if (!isCurrentSyncContext(context)) return;
    renderCommunityExamples();
    saveButton.disabled = false;
    deleteButton.disabled = false;
    setMessage(message, "Votre exemple a été supprimé. L’exemple éditorial est de nouveau affiché.", "success");
  });
});

const toggleExampleHeart = async (exampleId, gallery) => {
  if (!state.user) return openAuthDialog();
  const context = captureSyncContext();
  const status = gallery.querySelector("[data-examples-status]");
  if (!state.personalHeartsReady) {
    return setMessage(status, "Le vote n’est pas disponible pour le moment.", "error");
  }
  const examples = state.communityExamples.get(gallery.dataset.biasId) || [];
  const example = examples.find((candidate) => candidate.example_id === exampleId);
  if (!example) return;
  const button = gallery.querySelector(`[data-example-heart="${exampleId}"]`);
  if (button) button.disabled = true;
  const liked = state.personalHeartIds.has(exampleId);
  const request = liked
    ? supabase
      .from("bias_example_hearts")
      .delete()
      .eq("user_id", context.userId)
      .eq("example_id", exampleId)
    : supabase
      .from("bias_example_hearts")
      .insert({ user_id: context.userId, example_id: exampleId });
  const { error } = await request;
  if (!isCurrentSyncContext(context)) return;
  if (error) {
    if (button) button.disabled = false;
    return setMessage(status, error.message, "error");
  }
  if (liked) {
    state.personalHeartIds.delete(exampleId);
    example.heart_count = Math.max(0, example.heart_count - 1);
  } else {
    state.personalHeartIds.add(exampleId);
    example.heart_count += 1;
  }
  renderCommunityExamples();
  gallery.querySelector(`[data-example-heart="${exampleId}"]`)?.focus();
  setMessage(
    status,
    liked ? "Votre cœur a été retiré." : "Votre cœur a été ajouté.",
    "success",
  );
};

document.querySelectorAll("[data-examples-more]").forEach((button) => {
  button.addEventListener("click", () => {
    const gallery = button.closest("[data-example-gallery]");
    gallery.dataset.visibleCount = String(Number.parseInt(gallery.dataset.visibleCount || "12", 10) + 12);
    renderCommunityExamples();
  });
});

document.querySelectorAll("[data-examples-retry]").forEach((button) => {
  button.addEventListener("click", async () => {
    const context = captureSyncContext();
    state.communityExamplesError = false;
    state.communityExamplesReady = false;
    state.personalHeartsError = false;
    state.personalHeartsReady = false;
    renderCommunityExamples();
    await loadCommunityExamples(context);
    if (!isCurrentSyncContext(context)) return;
    await loadPersonalHearts(context);
    if (!isCurrentSyncContext(context)) return;
    renderCommunityExamples();
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
  syncEpoch += 1;
  state.user = user;
  const context = captureSyncContext();
  state.profile = null;
  state.personal.clear();
  state.personalReady = false;
  state.personalExamples.clear();
  state.personalExamplesReady = false;
  state.personalExamplesError = false;
  state.personalHeartIds.clear();
  state.personalHeartsReady = false;
  state.personalHeartsError = false;
  state.canReview = false;
  document.querySelectorAll("[data-example-message]").forEach((message) => {
    setMessage(message, "");
  });
  renderAuth();
  renderReviewerAccess();
  renderPersonalExamples();
  renderPersonalExampleEditors();
  renderCommunityExamples();
  publishPersonalRatingState();

  await Promise.all([
    loadProfile(context),
    loadPersonalRatings(context),
    loadAggregates(context),
    loadReviewerAccess(context),
    loadPersonalExamples(context),
    loadCommunityExamples(context),
  ]);
  if (!isCurrentSyncContext(context)) return;
  await loadPersonalHearts(context);
  if (!isCurrentSyncContext(context)) return;
  renderAuth();
  renderReviewerAccess();
  renderPersonalExamples();
  renderPersonalExampleEditors();
  renderCommunityExamples();
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
