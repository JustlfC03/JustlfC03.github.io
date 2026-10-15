/* Navigation and optional citation counts; page content also works without JS. */
(function () {
  "use strict";

  var script = document.currentScript;
  var navLinks = Array.from(document.querySelectorAll(".home-wordmark, .home-nav a"));
  var sections = navLinks.map(function (link) {
    return document.getElementById(link.hash.slice(1));
  }).filter(Boolean);

  function setupOverflowNavigation() {
    var nav = document.querySelector(".home-nav");
    if (!nav) return;
    var inlineLinks = nav.querySelector(".home-nav__links");
    var more = nav.querySelector(".home-nav__more");
    var toggle = nav.querySelector(".home-nav__toggle");
    var menu = nav.querySelector(".home-nav__menu");
    if (!inlineLinks || !more || !toggle || !menu) return;
    var links = Array.from(nav.querySelectorAll("a"));
    var layoutScheduled = false;

    function layoutNavigation() {
      layoutScheduled = false;
      var focused = document.activeElement;
      var wasOpen = more.open;
      var navStyle = window.getComputedStyle(nav);
      var available = nav.getBoundingClientRect().width
        - (parseFloat(navStyle.paddingLeft) || 0) - (parseFloat(navStyle.paddingRight) || 0)
        - (parseFloat(navStyle.borderLeftWidth) || 0) - (parseFloat(navStyle.borderRightWidth) || 0);
      if (available <= 0) return;

      // Measure every link in its inline style, including links currently hidden.
      inlineLinks.hidden = false;
      more.hidden = false;
      links.forEach(function (link) { inlineLinks.appendChild(link); });
      var gap = parseFloat(window.getComputedStyle(inlineLinks).columnGap) || 0;
      var moreGap = parseFloat(navStyle.columnGap) || 0;
      var toggleWidth = more.getBoundingClientRect().width;
      var widths = links.map(function (link) { return link.getBoundingClientRect().width; });
      var allWidth = widths.reduce(function (sum, width) { return sum + width; }, 0) + Math.max(0, links.length - 1) * gap;
      var count = links.length;

      if (allWidth > available) {
        count = 0;
        var used = 0;
        widths.some(function (width, index) {
          var nextWidth = used + (index ? gap : 0) + width;
          if (nextWidth + moreGap + toggleWidth > available) return true;
          used = nextWidth;
          count += 1;
          return false;
        });
      }

      links.slice(count).forEach(function (link) { menu.appendChild(link); });
      inlineLinks.hidden = count === 0;
      more.hidden = count === links.length;
      more.open = wasOpen && !more.hidden;

      // Moving a focused node can blur it; keep keyboard focus on a visible control.
      if (links.indexOf(focused) !== -1) {
        var focusTarget = menu.contains(focused) && !more.open ? toggle : focused;
        focusTarget.focus({ preventScroll: true });
      } else if (focused === toggle && more.hidden && links.length) {
        links[links.length - 1].focus({ preventScroll: true });
      }
    }

    function scheduleLayout() {
      if (layoutScheduled) return;
      layoutScheduled = true;
      window.requestAnimationFrame(layoutNavigation);
    }

    var header = nav.closest(".home-header");
    if (header) header.addEventListener("click", function (event) {
      if (!event.target.closest("a")) return;
      if (menu.contains(document.activeElement)) toggle.focus({ preventScroll: true });
      more.open = false;
    });
    document.addEventListener("click", function (event) {
      if (!more.contains(event.target)) more.open = false;
    });
    document.addEventListener("keydown", function (event) {
      if (event.key !== "Escape" || !more.open) return;
      more.open = false;
      toggle.focus({ preventScroll: true });
      event.preventDefault();
    });
    window.addEventListener("resize", scheduleLayout);
    if (window.ResizeObserver) {
      var lastWidth = -1;
      var observer = new ResizeObserver(function (entries) {
        var width = entries[0].contentRect.width;
        if (Math.abs(width - lastWidth) < 0.1) return;
        lastWidth = width;
        scheduleLayout();
      });
      observer.observe(nav);
    }
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(scheduleLayout);
    layoutNavigation();
  }

  setupOverflowNavigation();

  function updateCurrentSection() {
    var current = sections[0];
    var currentTop = -Infinity;
    var header = document.querySelector(".home-header");
    var threshold = header ? header.getBoundingClientRect().height + 48 : 128;
    sections.forEach(function (section) {
      var top = section.getBoundingClientRect().top;
      // Side-by-side panels share a row; keep the explicitly selected panel active.
      var selectedOnSameRow = Math.abs(top - currentTop) <= 1 && location.hash === "#" + section.id;
      if (top <= threshold && (top > currentTop + 1 || selectedOnSameRow)) {
        current = section;
        currentTop = top;
      }
    });
    navLinks.forEach(function (link) {
      if (current && link.hash === "#" + current.id) {
        link.setAttribute("aria-current", "location");
      } else {
        link.removeAttribute("aria-current");
      }
    });
  }

  var scheduled = false;
  window.addEventListener("scroll", function () {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(function () {
      updateCurrentSection();
      scheduled = false;
    });
  }, { passive: true });
  window.addEventListener("resize", updateCurrentSection);
  window.addEventListener("hashchange", updateCurrentSection);
  updateCurrentSection();

  // Preserve new-tab behavior for external references, while anchors stay in-page.
  document.querySelectorAll(".page__content a[href^='https://']").forEach(function (link) {
    link.target = "_blank";
    link.rel = "noopener noreferrer";
  });

  var url = script && script.getAttribute("data-scholar-url");
  if (!url || !window.fetch) return;
  fetch(url).then(function (response) {
    if (!response.ok) throw new Error("Citation data unavailable");
    return response.json();
  }).then(function (data) {
    document.querySelectorAll(".show_paper_citations").forEach(function (element) {
      var paper = data.publications && data.publications[element.getAttribute("data")];
      if (!paper || paper.num_citations == null) return;
      var count = Number(paper.num_citations);
      if (Number.isInteger(count) && count >= 0) element.textContent = "Citations: " + count;
    });
  }).catch(function () {
    // External citation data is optional; the Scholar links remain available.
  });
})();
