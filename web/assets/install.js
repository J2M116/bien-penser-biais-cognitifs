(() => {
  const installButtons = Array.from(document.querySelectorAll("[data-install-open]"));
  const dialog = document.querySelector("#install-dialog");
  const iosInstructions = dialog?.querySelector("[data-install-ios-instructions]");
  const browserInstructions = dialog?.querySelector("[data-install-browser-instructions]");
  const confirmButton = dialog?.querySelector("[data-install-confirm]");
  let installPrompt = null;

  const isStandalone = () => (
    window.matchMedia("(display-mode: standalone)").matches
    || window.navigator.standalone === true
  );
  const isIos = () => (
    /iPhone|iPad|iPod/.test(window.navigator.userAgent)
    || (window.navigator.platform === "MacIntel" && window.navigator.maxTouchPoints > 1)
  );

  const setButtonsVisible = (visible) => {
    installButtons.forEach((button) => {
      button.hidden = !visible;
    });
  };

  const refresh = () => {
    setButtonsVisible(!isStandalone() && (isIos() || Boolean(installPrompt)));
  };

  installButtons.forEach((button) => {
    button.addEventListener("click", () => {
      if (!dialog || isStandalone()) return;
      const ios = isIos();
      if (iosInstructions) iosInstructions.hidden = !ios;
      if (browserInstructions) browserInstructions.hidden = ios || !installPrompt;
      if (!dialog.open) dialog.showModal();
    });
  });

  confirmButton?.addEventListener("click", async () => {
    if (!installPrompt) return;
    await installPrompt.prompt();
    await installPrompt.userChoice;
    installPrompt = null;
    dialog?.close();
    refresh();
  });

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    installPrompt = event;
    refresh();
  });

  window.addEventListener("appinstalled", () => {
    installPrompt = null;
    dialog?.close();
    refresh();
  });

  window.matchMedia("(display-mode: standalone)").addEventListener?.("change", refresh);
  refresh();
})();
