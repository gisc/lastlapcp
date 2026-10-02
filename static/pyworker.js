// Runs the drill checks off the page's main thread, so a student's infinite loop can be
// stopped (the page terminates this worker) instead of freezing the tab. Student code runs
// only here, in the student's own browser, never on the server.
importScripts(self.location.origin + '/static/pyodide/pyodide.js');
let py = null;
const ready = (async () => {
  py = await loadPyodide({ indexURL: self.location.origin + '/static/pyodide/' });
  postMessage({ t: 'ready' });
})().catch(err => { postMessage({ t: 'initfail', msg: String((err && err.message) || err) }); throw err; });
onmessage = async (e) => {
  const j = e.data;
  try { await ready; } catch (err) { return; }
  const lines = [];
  py.setStdout({ batched: s => lines.push(s) });
  py.setStderr({ batched: s => lines.push(s) });
  let passed = false, raw = '', ck = 0;
  try {
    py.globals.set('_SRC', j.code);
    if (j.html !== null && j.html !== undefined) py.globals.set('_HTML', j.html);
    py.runPython('_CK = set()');
    if (j.pkgs && j.pkgs.length) await py.loadPackage(j.pkgs);
    if (j.kind === 'script') await py.runPythonAsync(j.resetdb);
    if (j.kind === 'sql' || j.kind === 'webapp') await py.runPythonAsync(j.tests);
    else await py.runPythonAsync(j.code + '\n\n' + j.tests);
    passed = true;
  } catch (err) { raw = (err && err.message) || String(err); }
  try { ck = py.runPython('len(_CK)'); } catch (err) {}
  postMessage({ t: 'done', id: j.id, passed, raw, lines, ck });
};
