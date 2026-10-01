/* Line numbers for code editors, and error lines mapped back to the student's own code.
   Pyodide runs: student code + blank line + hidden checker. Tracebacks count lines across
   both, so a line past the student's last line belongs to the hidden checker. */
(function () {
  function attach(ta) {
    var wrap = document.createElement('div');
    wrap.className = 'codewrap';
    var gut = document.createElement('div');
    gut.className = 'gutter';
    gut.setAttribute('aria-hidden', 'true');
    ta.parentNode.insertBefore(wrap, ta);
    wrap.appendChild(gut);
    wrap.appendChild(ta);
    ta.setAttribute('wrap', 'off');
    var bad = 0, count = 0;
    function draw() {
      var n = ta.value.split('\n').length;
      if (n === count && !draw.force) { gut.scrollTop = ta.scrollTop; return; }
      count = n; draw.force = false;
      var h = '';
      for (var i = 1; i <= n; i++) h += '<span' + (i === bad ? ' class="errline"' : '') + '>' + i + '</span>';
      gut.innerHTML = h;
      gut.scrollTop = ta.scrollTop;
    }
    ta.addEventListener('input', draw);
    ta.addEventListener('scroll', function () { gut.scrollTop = ta.scrollTop; });
    draw();
    return {
      refresh: draw,
      mark: function (n) {
        bad = n || 0; draw.force = true; draw();
        if (n) {
          var lh = parseFloat(getComputedStyle(ta).lineHeight) || 22;
          ta.scrollTop = Math.max(0, (n - 3) * lh);
          gut.scrollTop = ta.scrollTop;
        }
      }
    };
  }
  /* Rewrites `File "<exec>", line N, in X` lines. Returns {text, line} where line is the
     last student-code line named in the traceback (0 if none). */
  function fixTrace(text, nStudent) {
    var last = 0;
    var out = text.split('\n').map(function (l) {
      var m = l.match(/File "<(?:exec|unknown)>", line (\d+)(?:, in (.+))?/);
      if (!m) return l;
      var n = parseInt(m[1], 10), where = m[2] && m[2] !== '<module>' ? ' (in ' + m[2] + ')' : '';
      if (n <= nStudent) { last = n; return 'Your code, line ' + n + where; }
      return 'Checker test (hidden, not a line in your code)';
    });
    return { text: out.join('\n'), line: last };
  }
  window.CodeEdit = { attach: attach, fixTrace: fixTrace };
})();
