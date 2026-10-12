// VRIOSCU website — progressive enhancement only. Every page works without JS.
(function () {
  "use strict";
  document.documentElement.classList.remove("no-js");

  var toggle = document.querySelector(".nav-toggle");
  var nav = document.getElementById("site-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!open));
      nav.classList.toggle("is-open", !open);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {
        toggle.setAttribute("aria-expanded", "false");
        nav.classList.remove("is-open");
        toggle.focus();
      }
    });
  }

  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.confirm(form.getAttribute("data-confirm"))) e.preventDefault();
    });
  });

  var summary = document.querySelector(".error-summary");
  if (summary) summary.focus();
})();
// A scroll-linked demonstration. Scrolling selects evidence, never runs a check.
(function () {
  var root = document.querySelector('[data-evidence-story]');
  if (!root) return;
  var scenes = Array.from(root.querySelectorAll('[data-scene]'));
  var previews = Array.from(root.querySelectorAll('[data-preview]'));
  var links = Array.from(root.querySelectorAll('[data-stage-link]'));
  var scheduled = false;
  function update() {
    scheduled = false;
    var anchor = innerHeight * .45;
    var chosen = scenes.reduce(function (best, scene) {
      return Math.abs(scene.getBoundingClientRect().top + scene.offsetHeight / 2 - anchor) < Math.abs(best.getBoundingClientRect().top + best.offsetHeight / 2 - anchor) ? scene : best;
    }, scenes[0]);
    var key = chosen.dataset.scene;
    if (root.dataset.activeScene === key) return;
    root.dataset.activeScene = key;
    previews.forEach(function (pane) { pane.hidden = pane.dataset.preview !== key; });
    links.forEach(function (link) {
      if (link.dataset.stageLink === key) link.setAttribute('aria-current','step');
      else link.removeAttribute('aria-current');
    });
    root.querySelector('[data-scene-label]').textContent = '0' + (scenes.indexOf(chosen) + 1) + ' / ' + key.toUpperCase();
  }
  function schedule() { if (!scheduled) { scheduled = true; requestAnimationFrame(update); } }
  addEventListener('scroll',schedule,{passive:true});
  addEventListener('resize',schedule);
  update();
})();

(function () {
  var toggle = document.querySelector('[data-theme-toggle]');
  function label() {
    if (!toggle) return;
    var next = document.documentElement.dataset.theme === 'light' ? 'Dark' : 'Light';
    toggle.textContent = next + ' mode';
    toggle.setAttribute('aria-label','Switch to ' + next.toLowerCase() + ' mode');
    document.querySelector('meta[name=theme-color]').content = next === 'Dark' ? '#f7f9fc' : '#080b10';
  }
  if (toggle) toggle.addEventListener('click',function () {
    var theme = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('vrioscu-theme',theme); } catch (_) {}
    label();
  });
  matchMedia('(prefers-color-scheme: light)').addEventListener('change',function (event) {
    var saved = null;
    try { saved = localStorage.getItem('vrioscu-theme'); } catch (_) {}
    if (!saved) document.documentElement.dataset.theme = event.matches ? 'light' : 'dark';
    label();
  });
  label();
})();

// Optional first-party analytics. No request before consent; no account tracking.
(function () {
  var token = document.querySelector('meta[name=csrf-token]').content;
  var allowedPage = document.body.dataset.trackPage === 'true';
  var blocked = navigator.doNotTrack === '1' || navigator.globalPrivacyControl === true;
  if (!allowedPage || blocked || document.body.dataset.analyticsChoice !== 'allow') return;
  var eventId = crypto.randomUUID ? crypto.randomUUID() : Array.from(crypto.getRandomValues(new Uint8Array(16))).map(function (n) { return n.toString(16).padStart(2,'0'); }).join('');
  var recorded = false;
  function event(kind) {
    fetch('/analytics/event',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':token},body:JSON.stringify({path:location.pathname,event_id:eventId,kind:kind,referrer:document.referrer})}).then(function (response) { if (response.ok && kind === 'view') recorded = true; }).catch(function () {});
  }
  event('view');
  setInterval(function () { if (!document.hidden && recorded) event('heartbeat'); },60000);
})();
// Fixed-width expanding report cards. Touch selects; only Explore opens a page.
(function () {
  "use strict";
  document.querySelectorAll('[data-report-rail]').forEach(function (rail) {
    var cards = Array.from(rail.querySelectorAll('[data-report-card]'));
    var buttons = cards.map(function (card) { return card.querySelector('[data-report-select]'); });
    var hover = matchMedia('(min-width:641px) and (hover:hover)');
    var focusSelection = false;
    function hoverSelect(event, index) {
      if (event.pointerType === 'mouse' && hover.matches && !rail.querySelector('[data-report-page]:focus')) select(index);
    }
    function select(index) {
      cards.forEach(function (card, i) {
        var active = i === index;
        card.classList.toggle('is-active', active);
        buttons[i].setAttribute('aria-expanded', String(active));
        card.querySelector('.rail-caption').setAttribute('aria-hidden', String(!active));
        card.querySelector('[data-report-page]').tabIndex = active ? 0 : -1;
      });
    }
    rail.classList.add('is-enhanced');
    select(0);
    cards.forEach(function (card, index) {
      buttons[index].hidden = false;
      card.addEventListener('pointerenter', function (event) {
        if (!focusSelection) hoverSelect(event, index);
      });
      card.addEventListener('pointermove', function (event) {
        if (event.movementX || event.movementY) {
          focusSelection = false;
          hoverSelect(event, index);
        }
      });
      card.addEventListener('focusin', function () { focusSelection = true; select(index); });
      buttons[index].addEventListener('click', function () { select(index); });
      buttons[index].addEventListener('keydown', function (event) {
        var next = index;
        if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (index + 1) % cards.length;
        else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (index + cards.length - 1) % cards.length;
        else if (event.key === 'Home') next = 0;
        else if (event.key === 'End') next = cards.length - 1;
        else return;
        event.preventDefault();
        buttons[next].focus({preventScroll:true});
      });
    });
  });
})();
// Local illustrations only: no validation requests or client-side AI inference.
(function () {
  "use strict";
  document.querySelectorAll("[data-workspace]").forEach(function (workspace) {
    var tabs = Array.from(workspace.querySelectorAll("[role=tab]"));
    var panels = Array.from(workspace.querySelectorAll("[role=tabpanel]"));
    var play = workspace.querySelector("[data-play]");
    var timer = null;
    var playing = false;
    function stop() {
      clearTimeout(timer);
      playing = false;
      play.textContent = "Play walkthrough ▷";
    }
    function select(index, focus) {
      tabs.forEach(function (tab, i) {
        tab.setAttribute("aria-selected", String(i === index));
        tab.tabIndex = i === index ? 0 : -1;
        panels[i].hidden = i !== index;
      });
      if (focus) tabs[index].focus();
    }
    tabs.forEach(function (tab, index) {
      tab.addEventListener("click", function () { stop(); select(index, false); });
      tab.addEventListener("keydown", function (event) {
        var next = index;
        if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
        else if (event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length;
        else if (event.key === "Home") next = 0;
        else if (event.key === "End") next = tabs.length - 1;
        else return;
        event.preventDefault(); stop(); select(next, true);
      });
    });
    play.hidden = false;
    play.addEventListener("click", function () {
      if (playing) { stop(); return; }
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { select(3, false); return; }
      playing = true;
      play.textContent = "Pause walkthrough Ⅱ";
      var index = 0;
      select(index, false);
      function advance() {
        index++;
        if (index === tabs.length) { stop(); return; }
        select(index, false);
        timer = setTimeout(advance, 2200);
      }
      timer = setTimeout(advance, 2200);
    });
    document.addEventListener("visibilitychange", function () { if (document.hidden) stop(); });
  });

  var dialog = document.querySelector(".report-lightbox");
  if (dialog && typeof dialog.showModal === "function") {
    var image = dialog.querySelector("[data-lightbox-image]");
    var original = dialog.querySelector("[data-image-original]");
    var title = document.getElementById("report-dialog-title");
    var opener = null;
    var zoom = dialog.querySelector('[data-report-zoom]');
    zoom.addEventListener('click',function () {
      var on = zoom.getAttribute('aria-pressed') !== 'true';
      zoom.setAttribute('aria-pressed',String(on));
      zoom.textContent = on ? 'Fit page' : 'Zoom in';
      dialog.classList.toggle('is-zoomed',on);
    });
    document.querySelectorAll("[data-report-page]").forEach(function (link) {
      link.addEventListener("click", function (event) {
        event.preventDefault();
        opener = link;
        zoom.setAttribute('aria-pressed','false');
        zoom.textContent = 'Zoom in';
        dialog.classList.remove('is-zoomed');
        image.src = link.href;
        var thumbnail = link.querySelector("img");
        image.alt = link.dataset.reportAlt || (thumbnail ? thumbnail.alt : link.getAttribute("data-report-title"));
        title.textContent = link.getAttribute("data-report-title");
        original.href = link.href;
        dialog.showModal();
      });
    });
    dialog.querySelector("[data-close-report]").addEventListener("click", function () { dialog.close(); });
    dialog.addEventListener("click", function (event) { if (event.target === dialog) dialog.close(); });
    dialog.addEventListener("close", function () { if (opener) opener.focus(); });
  }
})();
