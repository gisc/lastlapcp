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
    /* Python auto-indent: Enter keeps the current indent, adds 4 after a line ending in ":",
       and steps back 4 after return/pass/break/continue/raise. Backspace in leading spaces
       removes one indent level. Works with the iPad soft and hardware keyboards. */
    function fire(type) { ta.dispatchEvent(new InputEvent('input', { inputType: type, bubbles: true })); }
    ta.addEventListener('keydown', function (e) {
      if (e.isComposing || e.ctrlKey || e.metaKey || e.altKey) return;
      var a = ta.selectionStart, b = ta.selectionEnd;
      if (e.key === 'Enter') {
        e.preventDefault();
        var before = ta.value.slice(0, a);
        var line = before.slice(before.lastIndexOf('\n') + 1);
        var indent = line.match(/^ */)[0].length;
        var code = line.replace(/#.*$/, '').replace(/\s+$/, '');
        if (/:$/.test(code)) indent += 4;
        else if (/^\s*(return|pass|break|continue|raise)\b/.test(code) && indent >= 4) indent -= 4;
        ta.setRangeText('\n' + new Array(indent + 1).join(' '), a, b, 'end');
        fire('insertLineBreak');
        var lh = parseFloat(getComputedStyle(ta).lineHeight) || 22;
        var row = ta.value.slice(0, ta.selectionStart).split('\n').length;
        if ((row + 1) * lh > ta.scrollTop + ta.clientHeight) ta.scrollTop = (row + 1) * lh - ta.clientHeight;
      } else if (e.key === 'Backspace' && a === b && a > 0) {
        var bf = ta.value.slice(0, a);
        var ln = bf.slice(bf.lastIndexOf('\n') + 1);
        if (ln.length >= 4 && /^ +$/.test(ln) && ln.length % 4 === 0) {
          e.preventDefault();
          ta.setRangeText('', a - 4, a, 'end');
          fire('deleteContentBackward');
        }
      }
    });
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
    out = out.filter(function (l, i) { return i === 0 || l !== out[i - 1] || l.indexOf('Checker test') !== 0; });
    return { text: out.join('\n'), line: last };
  }
  window.CodeEdit = { attach: attach, fixTrace: fixTrace };
})();
