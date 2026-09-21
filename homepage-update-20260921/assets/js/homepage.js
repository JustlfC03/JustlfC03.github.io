/* Navigation and optional citation counts; page content also works without JS. */
(function () {
  "use strict";

  var script = document.currentScript;
  var navLinks = Array.from(document.querySelectorAll(".home-wordmark, .home-nav a"));
  var sections = navLinks.map(function (link) {
    return document.getElementById(link.hash.slice(1));
  }).filter(Boolean);

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

  // Move only the logo; keep the motto and its grid row in their original position.
  var motto = document.querySelector(".profile-bio");
  var labLogo = document.querySelector(".profile-lab-logo");
  if (motto && labLogo) {
    function alignLabLogo() {
      var mottoHeight = parseFloat(window.getComputedStyle(motto).height);
      var logoHeight = parseFloat(window.getComputedStyle(labLogo).height);
      labLogo.style.setProperty("--lab-logo-shift", (mottoHeight - logoHeight) / 2 + "px");
    }
    if (window.ResizeObserver) {
      var logoAlignmentObserver = new ResizeObserver(alignLabLogo);
      logoAlignmentObserver.observe(motto);
      logoAlignmentObserver.observe(labLogo);
    } else {
      window.addEventListener("resize", alignLabLogo);
    }
    alignLabLogo();
  }

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
