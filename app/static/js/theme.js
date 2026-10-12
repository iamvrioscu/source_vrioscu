// Blocking, self-hosted bootstrap: apply preference before the stylesheet paints.
(function () {
  var preference = null;
  try { preference = localStorage.getItem('vrioscu-theme'); } catch (_) {}
  var system = matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  document.documentElement.dataset.theme = /^(dark|light)$/.test(preference) ? preference : system;
})();
