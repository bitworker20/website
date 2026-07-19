(() => {
  "use strict";

  const header = document.querySelector(".site-header");
  const menuToggle = document.querySelector("[data-menu-toggle]");
  const navigation = document.querySelector("#primary-navigation");
  const desktopQuery = window.matchMedia("(min-width: 761px)");

  const setMenuState = (isOpen) => {
    if (!(header instanceof HTMLElement) || !(menuToggle instanceof HTMLButtonElement)) {
      return;
    }

    const nextState = String(isOpen);
    header.dataset.menuOpen = nextState;
    menuToggle.setAttribute("aria-expanded", nextState);
    menuToggle.setAttribute("aria-label", isOpen ? "Close navigation" : "Open navigation");
  };

  if (menuToggle instanceof HTMLButtonElement) {
    menuToggle.addEventListener("click", () => {
      const isOpen = menuToggle.getAttribute("aria-expanded") === "true";
      setMenuState(!isOpen);
    });
  }

  if (navigation instanceof HTMLElement) {
    navigation.addEventListener("click", (event) => {
      if (event.target instanceof HTMLAnchorElement) {
        setMenuState(false);
      }
    });
  }

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      setMenuState(false);
      menuToggle?.focus();
    }
  });

  desktopQuery.addEventListener("change", (event) => {
    if (event.matches) {
      setMenuState(false);
    }
  });

  const year = new Date().getFullYear();
  document.querySelectorAll("[data-current-year]").forEach((element) => {
    element.textContent = String(year);
  });
})();
