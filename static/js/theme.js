// Runs in <head> so the right theme is applied before first paint (no flash).
// Signed-in users get their saved theme from the server; guests follow the OS setting.
(function () {
  var root = document.documentElement;
  if (root.hasAttribute('data-guest') && window.matchMedia) {
    root.setAttribute('data-theme', window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
  }
})();
