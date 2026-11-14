// UI behaviour: sidebar, theme toggle, confirmations, upload dropzone, small form helpers.
(function () {
  'use strict';
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  // Sidebar (mobile)
  var sidebar = $('#sidebar'), scrim = $('#scrim'), menuBtn = $('#menuBtn');
  function toggleMenu(open) {
    if (!sidebar) return;
    sidebar.classList.toggle('open', open);
    if (scrim) scrim.classList.toggle('show', open);
  }
  if (menuBtn) menuBtn.addEventListener('click', function () { toggleMenu(!sidebar.classList.contains('open')); });
  if (scrim) scrim.addEventListener('click', function () { toggleMenu(false); });

  // Theme toggle (persisted on the server for the signed-in user)
  var themeBtn = $('#themeBtn');
  if (themeBtn) {
    themeBtn.addEventListener('click', function () {
      var next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      document.dispatchEvent(new CustomEvent('themechange'));
      var body = new URLSearchParams({ theme: next, csrf_token: themeBtn.dataset.csrf });
      fetch(themeBtn.dataset.url, { method: 'POST', body: body, headers: { 'X-CSRF-Token': themeBtn.dataset.csrf } })
        .catch(function () { /* theme still applies for this page view */ });
    });
  }

  // Confirm destructive actions
  $$('form[data-confirm]').forEach(function (f) {
    f.addEventListener('submit', function (e) { if (!window.confirm(f.dataset.confirm)) e.preventDefault(); });
  });

  // Animate score bars
  $$('.fill[data-width]').forEach(function (el) {
    var w = el.getAttribute('data-width');
    el.style.width = '0%';
    requestAnimationFrame(function () { requestAnimationFrame(function () { el.style.width = w + '%'; }); });
  });

  // Auto-submit selects and live range output
  $$('select[data-autosubmit]').forEach(function (s) { s.addEventListener('change', function () { s.form.submit(); }); });
  var range = $('#minRange'), out = $('#minOut');
  if (range && out) range.addEventListener('input', function () { out.textContent = range.value; });

  // Select-all for resume checklist
  var all = $('#selectAll');
  if (all) all.addEventListener('change', function () {
    $$('.checklist input[type=checkbox]').forEach(function (c) { c.checked = all.checked; });
  });

  // Upload dropzone
  var input = $('#fileInput'), list = $('#fileList'), btn = $('#uploadBtn'), zone = $('#dropzone');
  if (input && list) {
    var render = function () {
      list.innerHTML = '';
      Array.prototype.forEach.call(input.files, function (f) {
        var li = document.createElement('li');
        li.textContent = f.name + ' (' + Math.max(1, Math.round(f.size / 1024)) + ' KB)';
        var okType = /\.(pdf|docx)$/i.test(f.name);
        if (!okType) { li.className = 'bad'; li.textContent += ' - unsupported type'; }
        list.appendChild(li);
      });
      btn.disabled = input.files.length === 0;
    };
    input.addEventListener('change', render);
    ['dragenter', 'dragover'].forEach(function (ev) {
      zone.addEventListener(ev, function (e) { e.preventDefault(); zone.classList.add('over'); });
    });
    ['dragleave', 'drop'].forEach(function (ev) {
      zone.addEventListener(ev, function (e) { e.preventDefault(); zone.classList.remove('over'); });
    });
    zone.addEventListener('drop', function (e) {
      if (e.dataTransfer && e.dataTransfer.files.length) { input.files = e.dataTransfer.files; render(); }
    });
    $('#uploadForm').addEventListener('submit', function () { btn.disabled = true; btn.textContent = 'Analysing…'; });
  }
})();
