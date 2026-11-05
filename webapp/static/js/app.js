/* Progressive enhancement only: every page is readable without JavaScript. */
(function () {
  "use strict";

  var root = document.documentElement;

  /* Theme toggle ---------------------------------------------------------- */
  var toggle = document.querySelector("[data-theme-toggle]");
  if (toggle) {
    toggle.addEventListener("click", function () {
      var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try {
        window.localStorage.setItem("dz-theme", next);
      } catch (error) {
        /* storage can be unavailable in private mode; ignore */
      }
      toggle.setAttribute("aria-pressed", next === "dark" ? "true" : "false");
    });
  }

  /* Mobile navigation ----------------------------------------------------- */
  var navToggle = document.querySelector("[data-nav-toggle]");
  var nav = document.querySelector("[data-nav]");
  if (navToggle && nav) {
    navToggle.addEventListener("click", function () {
      var open = nav.classList.toggle("is-open");
      navToggle.setAttribute("aria-expanded", open ? "true" : "false");
    });

    window.addEventListener("resize", function () {
      if (window.innerWidth > 820) {
        nav.classList.remove("is-open");
        navToggle.setAttribute("aria-expanded", "false");
      }
    });
  }

  /* Filters are collapsible on small screens, always open on desktop ------ */
  var filters = document.querySelector("[data-filters]");
  if (filters) {
    var syncFilters = function () {
      if (window.innerWidth >= 1080) {
        filters.setAttribute("open", "");
      }
    };
    syncFilters();
    window.addEventListener("resize", syncFilters);
  }

  /* Avoid double submission on slow connections -------------------------- */
  var forms = document.querySelectorAll("form");
  for (var i = 0; i < forms.length; i += 1) {
    forms[i].addEventListener("submit", function () {
      var submit = this.querySelector('button[type="submit"]');
      if (submit && !submit.disabled) {
        submit.disabled = true;
        window.setTimeout(function () {
          submit.disabled = false;
        }, 8000);
      }
    });
  }
})();
