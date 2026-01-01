"""Page-injected event listener channel (002 D13 + the S1 SPA trio).

- listeners are registered on window in the capture phase (they fire before the React root's delegated handlers, so application-level stopPropagation cannot affect them);
- SPA routing has no real navigation events: listen explicitly for hashchange/popstate and wrap history.pushState/replaceState;
- events are passed back to Python with expose_binding (context level, survives real navigations).
Only raw facts are recorded: click / input (change/blur granularity, with value) / form submit / page navigation.
Redundant context for re-anchoring and diagnostics (text/tagName/ancestor-chain summary) is inlined with the accessibility information (002A, interpretation 2).
"""

BINDING_NAME = "__carverflow_emit"

INJECTION_JS = r"""
(() => {
  if (window.__carverflow_installed) return;
  window.__carverflow_installed = true;

  const emit = (payload) => {
    payload.ts = Date.now();
    payload.page_url = location.href;
    try { window.__carverflow_emit(JSON.stringify(payload)); } catch (e) { /* dropped while the binding is not ready */ }
  };

  const cssPath = (el) => {
    if (!(el instanceof Element)) return "";
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && parts.length < 12) {
      if (node.id) { parts.unshift("#" + CSS.escape(node.id)); break; }
      let part = node.localName;
      const parent = node.parentElement;
      if (parent) {
        const sibs = Array.from(parent.children).filter((c) => c.localName === node.localName);
        if (sibs.length > 1) part += ":nth-of-type(" + (sibs.indexOf(node) + 1) + ")";
      }
      parts.unshift(part);
      node = parent;
    }
    return parts.join(" > ");
  };

  const accName = (el) => {
    if (!el.getAttribute) return null;
    return (
      el.getAttribute("aria-label") ||
      el.getAttribute("placeholder") ||
      el.getAttribute("name") ||
      (el.textContent || "").trim().slice(0, 60) ||
      null
    );
  };

  const ancestors = (el) => {
    const out = [];
    let n = el.parentElement;
    while (n && out.length < 3) {
      let d = n.localName;
      if (n.id) d += "#" + n.id;
      else if (typeof n.className === "string" && n.className.trim())
        d += "." + n.className.trim().split(/\s+/).slice(0, 2).join(".");
      out.push(d);
      n = n.parentElement;
    }
    return out;
  };

  const describe = (el) => ({
    role: el.getAttribute ? el.getAttribute("role") : null,
    name: accName(el),
    tag: el.localName || null,
    text: ((el.textContent || "").trim().slice(0, 80)) || null,
    input_type: el instanceof HTMLInputElement ? el.type : null,
    ancestors: ancestors(el),
  });

  window.addEventListener(
    "click",
    (e) => {
      let el = e.target;
      if (el instanceof Element) el = el.closest("a,button,input,select,textarea,[role]") || el;
      if (!(el instanceof Element)) return;
      emit({ type: "click", selector: cssPath(el), ax: describe(el) });
    },
    true
  );

  window.addEventListener(
    "change",
    (e) => {
      const el = e.target;
      if (
        !(el instanceof HTMLInputElement) &&
        !(el instanceof HTMLTextAreaElement) &&
        !(el instanceof HTMLSelectElement)
      )
        return;
      emit({ type: "input", selector: cssPath(el), ax: describe(el), value: String(el.value) });
    },
    true
  );

  window.addEventListener(
    "submit",
    (e) => {
      if (!(e.target instanceof Element)) return;
      emit({ type: "submit", selector: cssPath(e.target), ax: describe(e.target) });
    },
    true
  );

  const navEvent = () =>
    emit({
      type: "navigate",
      selector: "",
      ax: { role: null, name: null, tag: null, text: null, input_type: null, ancestors: [] },
    });
  window.addEventListener("hashchange", navEvent);
  window.addEventListener("popstate", navEvent);
  const wrapHistory = (fn) =>
    function (...args) {
      const r = fn.apply(this, args);
      try { navEvent(); } catch (e) { /* noop */ }
      return r;
    };
  history.pushState = wrapHistory(history.pushState);
  history.replaceState = wrapHistory(history.replaceState);
})()
"""
