// PCL Playground — uses CodeMirror 5 (loaded via script tag) + Pyodide

(function () {

// =============================================================
// EXAMPLES
// =============================================================

const EXAMPLES = [
  {
    name: 'Hello PCL',
    pcl:
`# A simple greeting
@block greeting:
    Hello, \${name}! Welcome to PCL.

@include greeting`,
    vars: { name: 'World' },
  },
  {
    name: 'Blocks & includes',
    pcl:
`@block persona:
    You are a helpful assistant specialized in \${domain}.

@block footer:
    Always cite your sources.

@include persona

Your task: \${task}

@include footer`,
    vars: { domain: 'Python programming', task: 'Explain decorators' },
  },
  {
    name: 'Conditionals',
    pcl:
`You are an AI assistant.

@if premium:
    You have access to extended context and premium features.

@if not premium:
    Upgrade to premium for extended context.

The user's query: \${query | no query provided}`,
    vars: { premium: true, query: 'Explain transformers' },
  },
  {
    name: 'Raw block',
    pcl:
`You are a code assistant.

When calling a tool, always use this exact format:

@raw
    {"tool": "\${tool_name}", "args": {"input": "..."}}
@end

Never deviate from this schema.`,
    vars: {},
  },
  {
    name: 'Full example',
    pcl:
`---
version: 1.0
description: Research assistant
---

# Reusable date fragment
@block date_notice:
    Today's date is \${date}.

@block agent_setup:
    @include date_notice

# Main body
You are a research assistant.

@include agent_setup

@if premium:
    You also have access to the premium document index.

@if not premium:
    Upgrade to unlock the premium document index.

@raw
    When calling a tool, use this format:
    {"tool": "\${tool_name}", "args": {}}
@end

The user's query is: \${query | no query provided}`,
    vars: { date: '2026-03-15', premium: true, query: 'What is alignment?' },
  },
];

// =============================================================
// CodeMirror 5 — PCL mode
// =============================================================

CodeMirror.defineMode('pcl', function () {
  return {
    startState: function () {
      return { fm: 0, raw: false };
      // fm: 0=before frontmatter, 1=inside, 2=after
    },

    token: function (stream, state) {
      if (stream.sol()) {
        var line = stream.string;
        var trimmed = line.trim();

        // Frontmatter delimiter ---
        if (trimmed === '---') {
          if (state.fm === 0) state.fm = 1;
          else if (state.fm === 1) state.fm = 2;
          stream.skipToEnd();
          return 'meta';
        }

        // Inside frontmatter: YAML key
        if (state.fm === 1) {
          if (stream.match(/^[ \t]*\w[\w-]*(?=\s*:)/)) return 'property';
          stream.next();
          return null;
        }

        // @end exits raw block
        if (state.raw) {
          if (trimmed === '@end') {
            state.raw = false;
            stream.skipToEnd();
            return 'keyword';
          }
          stream.skipToEnd();
          return 'string';
        }

        // Comment line
        if (/^\s*#/.test(line)) {
          stream.skipToEnd();
          return 'comment';
        }

        // @raw
        if (/^\s*@raw(\s|$)/.test(line)) {
          state.raw = true;
          stream.eatSpace();
          stream.match(/@raw/);
          return 'keyword';
        }

        // Other @ directives
        if (/^\s*@/.test(line)) {
          stream.eatSpace();
          if (stream.match(/@if\s+not\b/) ||
              stream.match(/@if\b/)       ||
              stream.match(/@block\b/)    ||
              stream.match(/@include\b/)  ||
              stream.match(/@import\b/)   ||
              stream.match(/@end\b/)) {
            return 'keyword';
          }
        }
      }

      // Inline ${...} interpolation
      if (stream.match('${')) {
        while (!stream.eol() && stream.peek() !== '}') stream.next();
        if (!stream.eol()) stream.next();
        return 'atom';
      }

      stream.next();
      return null;
    },

    blankLine: function () {},

    copyState: function (state) {
      return { fm: state.fm, raw: state.raw };
    },
  };
});

// =============================================================
// State
// =============================================================

var pyodide       = null;
var isReady       = false;
var currentVars   = {};
var varList       = [];   // [{key, value}] where value is string or boolean
var debounceTimer = null;
var outputText    = '';
var currentExampleIdx = 0;
var lastLoadedPcl = '';
var editor        = null;

// =============================================================
// Helpers
// =============================================================

function setStatus(state, message) {
  var dot = document.getElementById('pg-status-dot');
  var msg = document.getElementById('pg-status-msg');
  if (!dot || !msg) return;
  dot.className = 'pg-status-dot pg-dot-' + state;
  msg.textContent = message;
}

function syncVarsFromList() {
  currentVars = {};
  for (var i = 0; i < varList.length; i++) {
    var k = varList[i].key.trim();
    if (k) currentVars[k] = varList[i].value;
  }
}

function scheduleCompile() {
  clearTimeout(debounceTimer);
  if (!isReady) return;
  debounceTimer = setTimeout(compile, 600);
}

// =============================================================
// Variables panel
// =============================================================

function renderVarsPanel() {
  var container = document.getElementById('pg-vars-rows');
  if (!container) return;
  container.innerHTML = '';

  varList.forEach(function (item, idx) {
    var row = document.createElement('div');
    row.className = 'pg-var-row';

    var keyInput = document.createElement('input');
    keyInput.type = 'text';
    keyInput.className = 'pg-var-input';
    keyInput.value = item.key;
    keyInput.placeholder = 'variable name';
    keyInput.addEventListener('input', function () {
      varList[idx].key = keyInput.value;
      syncVarsFromList();
      scheduleCompile();
    });

    if (typeof item.value === 'boolean') {
      var label = document.createElement('label');
      label.className = 'pg-var-bool-label';
      var cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = item.value;
      cb.addEventListener('change', function () {
        varList[idx].value = cb.checked;
        syncVarsFromList();
        scheduleCompile();
      });
      label.append(cb, document.createTextNode('\u00a0true/false'));
      row.append(keyInput, label);
    } else {
      var valInput = document.createElement('input');
      valInput.type = 'text';
      valInput.className = 'pg-var-input';
      valInput.value = item.value;
      valInput.placeholder = 'value';
      valInput.addEventListener('input', function () {
        varList[idx].value = valInput.value;
        syncVarsFromList();
        scheduleCompile();
      });
      row.append(keyInput, valInput);
    }

    var removeBtn = document.createElement('button');
    removeBtn.className = 'pg-var-remove';
    removeBtn.textContent = '\u00d7';
    removeBtn.title = 'Remove variable';
    removeBtn.addEventListener('click', function () {
      varList.splice(idx, 1);
      syncVarsFromList();
      renderVarsPanel();
      scheduleCompile();
    });
    row.append(removeBtn);

    container.append(row);
  });
}

// =============================================================
// Load example
// =============================================================

function loadExample(idx) {
  var ex = EXAMPLES[idx];
  var currentContent = editor ? editor.getValue() : '';

  if (currentContent !== lastLoadedPcl && currentContent.trim() !== '') {
    if (!confirm('Loading this example will replace your current code. Continue?')) {
      document.getElementById('pg-example-select').value = String(currentExampleIdx);
      return;
    }
  }

  currentExampleIdx = idx;
  lastLoadedPcl = ex.pcl;

  if (editor) editor.setValue(ex.pcl);

  varList = Object.entries(ex.vars).map(function (_ref) {
    return { key: _ref[0], value: _ref[1] };
  });
  syncVarsFromList();
  renderVarsPanel();
  scheduleCompile();
}

// =============================================================
// Compile via Pyodide
// =============================================================

async function compile() {
  if (!isReady || !editor) return;

  var source = editor.getValue();

  // @import guard
  var lines = source.split('\n');
  for (var i = 0; i < lines.length; i++) {
    var trimmed = lines[i].trim();
    if (trimmed.startsWith('#')) continue;
    if (/^@import\b/.test(trimmed)) {
      setStatus('error', '\u2715 @import is not supported in the playground');
      document.getElementById('pg-output').textContent = '';
      outputText = '';
      return;
    }
  }

  setStatus('compiling', 'Compiling\u2026');

  try {
    pyodide.FS.writeFile('/tmp/playground.pcl', source);
    pyodide.globals.set('_vars', pyodide.toPy(currentVars));

    var result = await pyodide.runPythonAsync(`
import pcl

try:
    _rendered = pcl.render('/tmp/playground.pcl', variables=dict(_vars))
    _output = ('ok', _rendered)
except Exception as e:
    _output = ('error', str(e))

_output
`);

    var parts = result.toJs();
    var status = parts[0];
    var value  = parts[1];

    if (status === 'ok') {
      outputText = value;
      document.getElementById('pg-output').textContent = value;
      var lineCount = value.split('\n').filter(function (l) { return l.trim(); }).length;
      setStatus('success', '\u2713 Compiled \u2014 ' + lineCount + ' line' + (lineCount !== 1 ? 's' : ''));
    } else {
      outputText = '';
      document.getElementById('pg-output').textContent = '';
      setStatus('error', '\u2715 ' + value);
    }
  } catch (err) {
    setStatus('error', '\u2715 ' + err.message);
  }
}

// =============================================================
// Pyodide loading
// =============================================================

async function initPyodide() {
  setStatus('loading', 'Loading compiler\u2026');
  try {
    pyodide = await loadPyodide({
      indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.27.5/full/',
    });
    await pyodide.loadPackage(['micropip', 'pyyaml']);
    await pyodide.runPythonAsync(`
import sys, micropip
from types import ModuleType
# Stub watchdog so micropip thinks it's installed and runtime imports don't fail.
# pcl.compile/render never actually use it — only the CLI watch command does.
for _m in ['watchdog', 'watchdog.events', 'watchdog.observers', 'watchdog.observers.polling']:
    sys.modules.setdefault(_m, ModuleType(_m))
micropip.add_mock_package('watchdog', '6.0.0')
await micropip.install('pcl-lang')
`);
    isReady = true;
    setStatus('ready', 'Ready');
    var compileBtn = document.getElementById('pg-compile-btn');
    if (compileBtn) compileBtn.disabled = false;
    scheduleCompile();
  } catch (err) {
    setStatus('error', 'Failed to load compiler: ' + err.message);
  }
}

// =============================================================
// Init
// =============================================================

function init() {
  var editorEl = document.getElementById('pg-editor-cm');
  if (!editorEl) return;

  // Prime state from first example
  var initial = EXAMPLES[0];
  lastLoadedPcl = initial.pcl;
  varList = Object.entries(initial.vars).map(function (_ref) {
    return { key: _ref[0], value: _ref[1] };
  });
  syncVarsFromList();

  // Create CM5 editor
  editor = CodeMirror(editorEl, {
    value:          initial.pcl,
    mode:           'pcl',
    theme:          'pcl-dark',
    lineNumbers:    true,
    indentUnit:     4,
    tabSize:        4,
    indentWithTabs: false,
    lineWrapping:   false,
    autofocus:      false,
  });

  renderVarsPanel();

  // Change listener → debounced compile
  editor.on('change', function () { scheduleCompile(); });

  // Example selector
  var select = document.getElementById('pg-example-select');
  if (select) {
    select.addEventListener('change', function () {
      loadExample(Number(select.value));
    });
  }

  // Variables toggle
  var varsToggle = document.getElementById('pg-vars-toggle');
  var varsPanel  = document.getElementById('pg-vars-panel');
  if (varsToggle && varsPanel) {
    varsToggle.addEventListener('click', function () {
      var hidden = varsPanel.hasAttribute('hidden');
      if (hidden) {
        varsPanel.removeAttribute('hidden');
        varsToggle.setAttribute('aria-expanded', 'true');
      } else {
        varsPanel.setAttribute('hidden', '');
        varsToggle.setAttribute('aria-expanded', 'false');
      }
    });
  }

  // Add variable row
  var addVarBtn = document.getElementById('pg-add-var');
  if (addVarBtn) {
    addVarBtn.addEventListener('click', function () {
      varList.push({ key: '', value: '' });
      syncVarsFromList();
      renderVarsPanel();
      var rows = document.querySelectorAll('.pg-var-row');
      if (rows.length) {
        var inp = rows[rows.length - 1].querySelector('.pg-var-input');
        if (inp) inp.focus();
      }
    });
  }

  // Compile button
  var compileBtn = document.getElementById('pg-compile-btn');
  if (compileBtn) {
    compileBtn.addEventListener('click', function () {
      clearTimeout(debounceTimer);
      compile();
    });
  }

  // Copy output button
  var copyBtn = document.getElementById('pg-copy-btn');
  if (copyBtn) {
    copyBtn.addEventListener('click', async function () {
      if (!outputText) return;
      try {
        await navigator.clipboard.writeText(outputText);
        var orig = copyBtn.textContent;
        copyBtn.textContent = 'Copied!';
        setTimeout(function () { copyBtn.textContent = orig; }, 2000);
      } catch (_) {}
    });
  }

  // Boot Pyodide
  initPyodide();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

})();
