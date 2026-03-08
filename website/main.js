// PCL Website — main.js

// ----------- Nav transparency on scroll -----------

(function () {
  const nav = document.getElementById('nav');
  const hero = document.getElementById('hero');

  if (!nav || !hero) return;

  const observer = new IntersectionObserver(
    ([entry]) => {
      nav.classList.toggle('scrolled', !entry.isIntersecting);
    },
    { threshold: 0.05 }
  );

  observer.observe(hero);
})();

// ----------- Copy button -----------

function setupCopyButton(btnId, text) {
  const btn = document.getElementById(btnId);
  if (!btn) return;

  btn.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(text);
      const tooltip = btn.querySelector('.copy-tooltip');
      if (tooltip) {
        tooltip.textContent = 'Copied!';
        tooltip.classList.add('show');
        setTimeout(() => {
          tooltip.classList.remove('show');
          tooltip.textContent = 'Copy';
        }, 2000);
      }
    } catch {
      // Clipboard API unavailable (e.g. file:// protocol)
    }
  });
}

setupCopyButton('copy-install', 'pip install pcl-lang');

// =================================================================
// HERO TYPING DEMO
// =================================================================

// --- Demo data ---

const DEMOS = [
  {
    filename: 'agent.pcl',
    vars: 'role, query',
    pcl:
`# Research assistant
@block persona:
    You are \${role}.

@include persona

Query: \${query}`,
    output:
`You are a research assistant.

Query: What is alignment?`,
  },
  {
    filename: 'agent.pcl',
    vars: 'premium, topic',
    pcl:
`@if premium:
    Extended context: on.

@if not premium:
    Upgrade for more context.

Summarise: \${topic | no topic given}`,
    output:
`Extended context: on.

Summarise: RAG pipelines`,
  },
  {
    filename: 'reviewer.pcl',
    vars: 'lang, snippet',
    pcl:
`---
description: Code reviewer
---

@block guide:
    Follow \${lang} best practices.

@include guide

Review this: \${snippet}`,
    output:
`Follow Python best practices.

Review this: def foo(): pass`,
  },
];

// --- Utility: sleep that can be cancelled via an AbortSignal ---

function sleep(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new DOMException('Aborted', 'AbortError'));
    const id = setTimeout(resolve, ms);
    signal?.addEventListener('abort', () => {
      clearTimeout(id);
      reject(new DOMException('Aborted', 'AbortError'));
    }, { once: true });
  });
}

// --- Mini PCL syntax highlighter (line-by-line) ---

function escapeHTML(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function highlightLine(raw) {
  const line = escapeHTML(raw);

  // Frontmatter delimiter
  if (/^---$/.test(raw.trim())) {
    return `<span class="pcl-frontmatter-delim">${line}</span>`;
  }

  // Comment
  if (/^\s*#/.test(raw)) {
    return `<span class="pcl-comment">${line}</span>`;
  }

  // YAML key (inside frontmatter — simple heuristic: no @ and contains ': ')
  if (/^\w[\w-]*:\s/.test(raw.trim()) && !/^@/.test(raw.trim())) {
    const m = raw.match(/^(\s*)(\w[\w-]*)(:.*)/);
    if (m) {
      return `${escapeHTML(m[1])}<span class="pcl-fm-key">${escapeHTML(m[2])}</span>${escapeHTML(m[3])}`;
    }
  }

  // @block name:
  {
    const m = raw.match(/^(\s*)(@block)(\s+)(\w+)(:)(.*)/);
    if (m) {
      let rest = highlightInterp(escapeHTML(m[6]));
      return `${escapeHTML(m[1])}<span class="pcl-keyword">${escapeHTML(m[2])}</span>${escapeHTML(m[3])}<span class="pcl-block-name">${escapeHTML(m[4])}</span>${escapeHTML(m[5])}${rest}`;
    }
  }

  // @if not
  if (/^\s*@if not\s/.test(raw)) {
    return raw.replace(/^(\s*)(@if not)(\s+)(\w+)(:)(.*)/, (_, ws, kw, sp, vr, col, rest) =>
      `${escapeHTML(ws)}<span class="pcl-keyword">${escapeHTML(kw)}</span>${escapeHTML(sp)}${escapeHTML(vr)}${escapeHTML(col)}${highlightInterp(escapeHTML(rest))}`
    );
  }

  // @if
  if (/^\s*@if\s/.test(raw)) {
    return raw.replace(/^(\s*)(@if)(\s+)(\w+)(:)(.*)/, (_, ws, kw, sp, vr, col, rest) =>
      `${escapeHTML(ws)}<span class="pcl-keyword">${escapeHTML(kw)}</span>${escapeHTML(sp)}${escapeHTML(vr)}${escapeHTML(col)}${highlightInterp(escapeHTML(rest))}`
    );
  }

  // @import, @include, @raw, @end
  {
    const m = raw.match(/^(\s*)(@import|@include|@raw|@end)(\s*)(.*)?$/);
    if (m) {
      let rest = escapeHTML(m[4] || '');
      if (m[2] === '@import') {
        rest = rest.replace(/(\.\/[\w./-]+)/, '<span class="pcl-path">$1</span>');
        rest = rest.replace(/\b(as)\b/, '<span class="pcl-keyword">as</span>');
      }
      rest = highlightInterp(rest);
      return `${escapeHTML(m[1])}<span class="pcl-keyword">${escapeHTML(m[2])}</span>${escapeHTML(m[3])}${rest}`;
    }
  }

  // Plain text — just highlight interpolations
  return highlightInterp(line);
}

function highlightInterp(escaped) {
  // ${var | default}
  escaped = escaped.replace(
    /(\$\{)([^|}]+?)(\s*\|\s*)([^}]+?)(\})/g,
    '<span class="pcl-interp-delim">$1</span><span class="pcl-var">$2</span><span class="pcl-default">$3$4</span><span class="pcl-interp-delim">$5</span>'
  );
  // ${var}
  escaped = escaped.replace(
    /(\$\{)(\w+)(\})/g,
    '<span class="pcl-interp-delim">$1</span><span class="pcl-var">$2</span><span class="pcl-interp-delim">$3</span>'
  );
  return escaped;
}

function highlightPCL(code) {
  return code.split('\n').map(highlightLine).join('\n');
}

// --- Typing animation ---

let abortController = null;

async function runTypingDemo() {
  const codeEl     = document.getElementById('demo-code');
  const outputEl   = document.getElementById('demo-output');
  const statusEl   = document.getElementById('demo-status');
  const cursorEl   = document.getElementById('demo-cursor');
  const filenameEl = document.getElementById('demo-filename');
  const varsBadge  = document.getElementById('demo-vars-badge');

  if (!codeEl) return;

  // Respect prefers-reduced-motion: show static last demo, no looping
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    const demo = DEMOS[0];
    codeEl.innerHTML = highlightPCL(demo.pcl);
    outputEl.textContent = demo.output;
    outputEl.style.opacity = '1';
    if (cursorEl) cursorEl.style.display = 'none';
    return;
  }

  let demoIndex = 0;

  while (true) {
    // Abort any previous sleep
    if (abortController) abortController.abort();
    abortController = new AbortController();
    const { signal } = abortController;

    const demo = DEMOS[demoIndex % DEMOS.length];
    demoIndex++;

    try {
      // --- Reset ---
      codeEl.innerHTML = '';
      outputEl.innerHTML = '';
      outputEl.style.transition = 'none';
      outputEl.style.opacity = '0';
      if (cursorEl) cursorEl.style.display = 'inline-block';
      if (filenameEl) filenameEl.textContent = demo.filename;
      if (varsBadge)  varsBadge.textContent  = demo.vars;
      statusEl.innerHTML = '<span class="status-dot status-ready">●</span> Ready';

      await sleep(600, signal);

      // --- Type code ---
      const text = demo.pcl;
      for (let i = 0; i <= text.length; i++) {
        codeEl.innerHTML = highlightPCL(text.slice(0, i));
        if (i < text.length) {
          const ch = text[i];
          // Slightly longer pause at newlines, otherwise 20–40 ms
          const delay = ch === '\n' ? 60 + Math.random() * 60
                                    : 18 + Math.random() * 18;
          await sleep(delay, signal);
        }
      }

      // --- Compile ---
      if (cursorEl) cursorEl.style.display = 'none';
      statusEl.innerHTML = '<span class="status-dot status-compiling">⟳</span> Compiling…';
      await sleep(650, signal);

      // --- Show output ---
      const lineCount = demo.output.split('\n').filter(l => l.trim()).length;
      statusEl.innerHTML = `<span class="status-dot status-success">✓</span> Compiled — ${lineCount} line${lineCount !== 1 ? 's' : ''}`;
      outputEl.textContent = demo.output;
      outputEl.style.transition = 'opacity 0.55s ease';
      outputEl.style.opacity = '1';

      // --- Hold ---
      await sleep(3200, signal);

      // --- Fade out before next cycle ---
      outputEl.style.transition = 'opacity 0.4s ease';
      outputEl.style.opacity = '0';
      await sleep(450, signal);

    } catch (e) {
      if (e.name !== 'AbortError') throw e;
      // Aborted — restart loop
    }
  }
}

// Start the demo after fonts/styles have settled
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => setTimeout(runTypingDemo, 300));
} else {
  setTimeout(runTypingDemo, 300);
}
