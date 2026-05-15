// Highlight the active sidebar item based on the current path
(function () {
  const path = window.location.pathname.replace(/\/$/, "");
  document.querySelectorAll(".menu-item").forEach((el) => {
    const href = (el.getAttribute("href") || "").replace(/\/$/, "");
    if (href && (path === href || path.startsWith(href + "/"))) {
      el.classList.add("is-active");
    }
  });
})();

// Preserve sidebar scroll position across navigations.
// The actual scroll container is `.sidebar-menu` (overflow-y: auto), not the
// outer `.sidebar` (which is sticky/full-height and doesn't scroll).
(function () {
  const scroller = document.querySelector(".sidebar-menu") ||
                   document.querySelector(".sidebar");
  if (!scroller) return;
  const KEY = "sidebar:scrollTop";

  // Restore as early as possible. If nothing is saved yet, scroll the active
  // item into view so the user always sees where they are.
  let restored = false;
  try {
    const saved = sessionStorage.getItem(KEY);
    if (saved !== null) {
      const top = parseInt(saved, 10) || 0;
      scroller.scrollTop = top;
      // Re-apply on next frame in case layout shifts after fonts/images load.
      requestAnimationFrame(() => { scroller.scrollTop = top; });
      restored = true;
    }
  } catch (e) {}
  if (!restored) {
    const active = scroller.querySelector(".menu-item.is-active");
    if (active && typeof active.scrollIntoView === "function") {
      active.scrollIntoView({ block: "nearest" });
    }
  }

  // Save on every scroll (rAF-throttled) and right before navigating away.
  let pending = false;
  function save() {
    try { sessionStorage.setItem(KEY, String(scroller.scrollTop)); } catch (e) {}
    pending = false;
  }
  scroller.addEventListener("scroll", () => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(save);
  }, { passive: true });
  // Capture intent-to-navigate clicks on any sidebar link
  const sidebar = document.querySelector(".sidebar") || scroller;
  sidebar.addEventListener("click", (e) => {
    const link = e.target.closest("a[href]");
    if (link) save();
  }, true);
  window.addEventListener("pagehide", save);
  window.addEventListener("beforeunload", save);
})();

// Sidebar collapse toggle (persists via localStorage)
(function () {
  const root = document.documentElement;
  const btn = document.getElementById("sidebar-toggle");
  if (!btn) return;

  function apply(state) {
    if (state === "collapsed") {
      root.setAttribute("data-sidebar", "collapsed");
      btn.setAttribute("aria-expanded", "false");
      btn.setAttribute("title", "Expand sidebar");
    } else {
      root.removeAttribute("data-sidebar");
      btn.setAttribute("aria-expanded", "true");
      btn.setAttribute("title", "Collapse sidebar");
    }
    try { localStorage.setItem("sidebar", state); } catch (e) {}
  }

  // Initialize aria/title from current state (set pre-paint in <head>)
  apply(root.getAttribute("data-sidebar") === "collapsed" ? "collapsed" : "expanded");

  btn.addEventListener("click", () => {
    const next = root.getAttribute("data-sidebar") === "collapsed" ? "expanded" : "collapsed";
    apply(next);
  });
})();

// Theme switch (Foundry Dark / Foundry White)
(function () {
  const root = document.documentElement;
  const buttons = document.querySelectorAll(".theme-switch__btn");
  if (!buttons.length) return;

  function apply(theme) {
    if (theme === "white") {
      root.setAttribute("data-theme", "white");
    } else {
      root.removeAttribute("data-theme");
    }
    try { localStorage.setItem("theme", theme); } catch (e) {}
    buttons.forEach((b) => {
      b.classList.toggle("is-active", b.dataset.themeSet === theme);
    });
  }

  let current = "white";
  try {
    if (localStorage.getItem("theme") === "dark") current = "dark";
  } catch (e) {}
  apply(current);

  buttons.forEach((b) => {
    b.addEventListener("click", () => apply(b.dataset.themeSet));
  });
})();

// Image lightbox — click any image in main content to view fullscreen with zoom
(function () {
  const main = document.querySelector(".main-area");
  if (!main) return;

  const images = main.querySelectorAll("img:not(.main-logo)");
  if (!images.length) return;

  // Build overlay once
  const overlay = document.createElement("div");
  overlay.className = "lightbox";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-hidden", "true");
  overlay.innerHTML = `
    <button type="button" class="lightbox__close" aria-label="Close">
      <i class="fa-solid fa-xmark"></i>
    </button>
    <button type="button" class="lightbox__btn lightbox__btn--out" aria-label="Zoom out">
      <i class="fa-solid fa-magnifying-glass-minus"></i>
    </button>
    <button type="button" class="lightbox__btn lightbox__btn--reset" aria-label="Reset zoom">
      <i class="fa-solid fa-expand"></i>
    </button>
    <button type="button" class="lightbox__btn lightbox__btn--in" aria-label="Zoom in">
      <i class="fa-solid fa-magnifying-glass-plus"></i>
    </button>
    <div class="lightbox__stage">
      <img class="lightbox__img" alt="">
    </div>
  `;
  document.body.appendChild(overlay);

  const stage   = overlay.querySelector(".lightbox__stage");
  const imgEl   = overlay.querySelector(".lightbox__img");
  const btnIn   = overlay.querySelector(".lightbox__btn--in");
  const btnOut  = overlay.querySelector(".lightbox__btn--out");
  const btnRst  = overlay.querySelector(".lightbox__btn--reset");
  const btnX    = overlay.querySelector(".lightbox__close");

  let scale = 1, tx = 0, ty = 0;
  let dragging = false, startX = 0, startY = 0, startTx = 0, startTy = 0;

  function applyTransform() {
    imgEl.style.transform = `translate(${tx}px, ${ty}px) scale(${scale})`;
    imgEl.style.cursor = scale > 1 ? (dragging ? "grabbing" : "grab") : "zoom-in";
  }

  function reset() {
    scale = 1; tx = 0; ty = 0;
    applyTransform();
  }

  function open(src, alt) {
    imgEl.src = src;
    imgEl.alt = alt || "";
    reset();
    overlay.classList.add("is-open");
    overlay.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  }

  function close() {
    overlay.classList.remove("is-open");
    overlay.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
    imgEl.src = "";
  }

  function zoom(delta, originX, originY) {
    const prev = scale;
    const next = Math.max(1, Math.min(6, scale + delta));
    if (next === prev) return;
    if (typeof originX === "number" && typeof originY === "number") {
      const rect = imgEl.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const ratio = next / prev;
      tx = (tx + cx - originX) * ratio + originX - cx;
      ty = (ty + cy - originY) * ratio + originY - cy;
    }
    scale = next;
    if (scale === 1) { tx = 0; ty = 0; }
    applyTransform();
  }

  // Wire up triggers
  images.forEach((img) => {
    img.style.cursor = "zoom-in";
    img.addEventListener("click", () => open(img.currentSrc || img.src, img.alt));
  });

  btnX.addEventListener("click", close);
  btnIn.addEventListener("click", () => zoom(0.5));
  btnOut.addEventListener("click", () => zoom(-0.5));
  btnRst.addEventListener("click", reset);

  // Click backdrop (not image / not buttons) closes
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay || e.target === stage) close();
  });

  // Image click toggles 1x ↔ 2x at click point
  imgEl.addEventListener("click", (e) => {
    e.stopPropagation();
    if (scale === 1) zoom(1, e.clientX, e.clientY);
    else reset();
  });

  // Wheel zoom
  stage.addEventListener("wheel", (e) => {
    e.preventDefault();
    zoom(e.deltaY < 0 ? 0.25 : -0.25, e.clientX, e.clientY);
  }, { passive: false });

  // Drag to pan when zoomed
  imgEl.addEventListener("pointerdown", (e) => {
    if (scale === 1) return;
    dragging = true;
    startX = e.clientX; startY = e.clientY;
    startTx = tx; startTy = ty;
    imgEl.setPointerCapture(e.pointerId);
    applyTransform();
  });
  imgEl.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    tx = startTx + (e.clientX - startX);
    ty = startTy + (e.clientY - startY);
    applyTransform();
  });
  function endDrag(e) {
    if (!dragging) return;
    dragging = false;
    try { imgEl.releasePointerCapture(e.pointerId); } catch (_) {}
    applyTransform();
  }
  imgEl.addEventListener("pointerup", endDrag);
  imgEl.addEventListener("pointercancel", endDrag);

  // Keyboard
  document.addEventListener("keydown", (e) => {
    if (!overlay.classList.contains("is-open")) return;
    if (e.key === "Escape") close();
    else if (e.key === "+" || e.key === "=") zoom(0.5);
    else if (e.key === "-" || e.key === "_") zoom(-0.5);
    else if (e.key === "0") reset();
  });
})();

// "Let's test" — live Azure AI Search panel on the Index & Retrieval page
(function () {
  const root = document.getElementById("search-tester");
  if (!root) return;

  // ---------- Auth (device-code sign-in inside the container) -------------
  const authBar       = root.querySelector("#auth-bar");
  const authTitle     = root.querySelector("#auth-bar__title");
  const authSubtitle  = root.querySelector("#auth-bar__subtitle");
  const authLoginBtn  = root.querySelector("#auth-bar__login");
  const authLogoutBtn = root.querySelector("#auth-bar__logout");

  const authModal      = root.querySelector("#auth-modal");
  const authModalCode  = root.querySelector("#auth-modal__code");
  const authModalUrl   = root.querySelector("#auth-modal__url");
  const authModalStatus = root.querySelector("#auth-modal__status");
  const authModalCancel = root.querySelector("#auth-modal__cancel");
  const authModalClose  = root.querySelector("#auth-modal__close");

  const API_BASE  = (root.dataset.apiBase || "/sections/index_retrieval_plan/api").replace(/\/$/, "");
  const AUTH_BASE = `${API_BASE}/auth`;
  let authState = "loading";   // "loading" | "ok" | "logged_out" | "pending" | "error"
  let authPollTimer = null;

  function setAuthState(state, payload) {
    authState = state;
    authBar.dataset.status = state === "pending" ? "logged_out" : state;
    if (state === "ok") {
      const acc = payload && payload.account;
      authTitle.textContent = "Signed in to Azure";
      authSubtitle.textContent = acc
        ? `${acc.user || "(unknown user)"} · ${acc.subscription_name || acc.subscription_id || ""}`
        : "Live search is enabled.";
      authLoginBtn.hidden = true;
      authLogoutBtn.hidden = false;
    } else if (state === "logged_out") {
      authTitle.textContent = "Not signed in";
      authSubtitle.textContent = "Click \"Sign in to Azure\" to authenticate this container with Entra ID. The credential is cached in a Docker volume.";
      authLoginBtn.hidden = false;
      authLogoutBtn.hidden = true;
    } else if (state === "pending") {
      authTitle.textContent = "Sign-in pending…";
      authSubtitle.textContent = "Complete the device-code flow in your browser.";
      authLoginBtn.hidden = false; authLoginBtn.disabled = true;
      authLogoutBtn.hidden = true;
    } else if (state === "error") {
      authTitle.textContent = "Sign-in failed";
      authSubtitle.textContent = (payload && payload.error) || "Try signing in again.";
      authLoginBtn.hidden = false; authLoginBtn.disabled = false;
      authLogoutBtn.hidden = true;
    } else {
      authTitle.textContent = "Checking sign-in…";
      authSubtitle.textContent = "";
      authLoginBtn.hidden = true; authLogoutBtn.hidden = true;
    }
  }

  function openAuthModal(code, url) {
    authModalCode.textContent = code || "—";
    if (url) {
      authModalUrl.textContent = url;
      authModalUrl.href = url;
    }
    authModalStatus.classList.remove("auth-modal__status--err");
    authModalStatus.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Waiting for you to complete sign-in…';
    authModal.hidden = false;
  }

  function closeAuthModal() {
    authModal.hidden = true;
    if (authPollTimer) { clearInterval(authPollTimer); authPollTimer = null; }
    authLoginBtn.disabled = false;
  }

  async function refreshAuthStatus() {
    try {
      const res = await fetch(`${AUTH_BASE}/status`);
      const data = await res.json().catch(() => ({}));
      if (data.status === "ok") {
        setAuthState("ok", data);
        if (!authModal.hidden) {
          authModalStatus.classList.remove("auth-modal__status--err");
          authModalStatus.innerHTML = '<i class="fa-solid fa-circle-check"></i> Signed in. Closing…';
          setTimeout(closeAuthModal, 700);
        }
        return data;
      }
      if (data.status === "pending") {
        setAuthState("pending", data);
        return data;
      }
      if (data.error) {
        setAuthState("error", data);
        return data;
      }
      setAuthState("logged_out");
      return data;
    } catch (err) {
      setAuthState("error", { error: err.message || String(err) });
      return null;
    }
  }

  authLoginBtn.addEventListener("click", async () => {
    authLoginBtn.disabled = true;
    setAuthState("pending");
    try {
      const res = await fetch(`${AUTH_BASE}/login`, { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setAuthState("error", { error: data.detail || `HTTP ${res.status}` });
        return;
      }
      if (data.status === "ok") {
        setAuthState("ok", data);
        return;
      }
      // pending — open modal and start polling
      openAuthModal(data.device_code, data.url);
      if (authPollTimer) clearInterval(authPollTimer);
      authPollTimer = setInterval(() => {
        refreshAuthStatus().then((d) => {
          if (d && d.status === "ok") {
            clearInterval(authPollTimer); authPollTimer = null;
          } else if (d && d.status === "logged_out" && d.error) {
            authModalStatus.classList.add("auth-modal__status--err");
            authModalStatus.textContent = "Sign-in failed: " + d.error;
            clearInterval(authPollTimer); authPollTimer = null;
          }
        });
      }, 3000);
    } catch (err) {
      setAuthState("error", { error: err.message || String(err) });
    }
  });

  authLogoutBtn.addEventListener("click", async () => {
    authLogoutBtn.disabled = true;
    try {
      await fetch(`${AUTH_BASE}/logout`, { method: "POST" });
    } finally {
      authLogoutBtn.disabled = false;
      setAuthState("logged_out");
    }
  });

  authModalCancel.addEventListener("click", closeAuthModal);
  authModalClose.addEventListener("click", closeAuthModal);
  authModal.addEventListener("click", (e) => { if (e.target === authModal) closeAuthModal(); });

  // Copy buttons inside the modal
  root.querySelectorAll("[data-copy]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const target = root.querySelector("#" + btn.dataset.copy);
      const text = target ? (target.textContent || target.value || "").trim() : "";
      if (!text) return;
      try {
        await navigator.clipboard.writeText(text);
        const orig = btn.innerHTML;
        btn.innerHTML = '<i class="fa-solid fa-check"></i> Copied';
        setTimeout(() => { btn.innerHTML = orig; }, 1200);
      } catch (_) {}
    });
  });

  // Initial status check
  refreshAuthStatus();

  // ---------- Search form -------------------------------------------------
  const MODE        = root.dataset.mode || "single";
  const form        = root.querySelector("#search-tester__form");
  const patternSel  = root.querySelector("#search-tester__pattern");
  const filterRow   = root.querySelector("#search-tester__filter-row");
  const submitBtn   = root.querySelector(".search-tester__submit");
  const statusEl    = root.querySelector("#search-tester__status");
  const resultsEl   = root.querySelector("#search-tester__results");
  const metaEl      = root.querySelector("#search-tester__meta");
  const tbodyEl     = root.querySelector("#search-tester__tbody");
  // Compare-mode elements (search_experience page)
  const compareEl   = root.querySelector("#search-tester__compare");
  const compareTheadEl = root.querySelector("#search-tester__compare-thead");
  const compareTbodyEl = root.querySelector("#search-tester__compare-tbody");

  const patternLabel = {
    keyword:  "Keyword (BM25)",
    hybrid:   "Hybrid + integrated vectorizer",
    filtered: "Filtered hybrid",
    vector:   "Pure vector",
    semantic: "Semantic ranker",
  };

  function syncFilterVisibility() {
    if (!filterRow || !patternSel) return;
    filterRow.hidden = patternSel.value !== "filtered";
  }
  if (patternSel) {
    patternSel.addEventListener("change", syncFilterVisibility);
    syncFilterVisibility();
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function setStatus(text, kind) {
    statusEl.className = "search-tester__status" + (kind ? " search-tester__status--" + kind : "");
    statusEl.textContent = text || "";
  }

  function renderResults(payload) {
    metaEl.textContent =
      `Pattern: ${patternLabel[payload.pattern] || payload.pattern} · `
      + `${payload.count} result${payload.count === 1 ? "" : "s"} · `
      + `${payload.elapsed_ms} ms`
      + (payload.filter ? ` · filter: ${payload.filter}` : "");

    if (!payload.results.length) {
      tbodyEl.innerHTML = `<tr><td colspan="7" class="muted" style="text-align:center; padding:18px;">No matches.</td></tr>`;
    } else {
      tbodyEl.innerHTML = payload.results.map((r, i) => {
        const scorePill = `<span class="score-pill" title="@search.score">${r.score.toFixed(3)}</span>`;
        const rerankerPill = (r.reranker_score != null)
          ? `<span class="score-pill score-pill--reranker" title="@search.rerankerScore">${r.reranker_score.toFixed(3)}</span>`
          : "";
        return `
        <tr>
          <td class="muted">${i + 1}</td>
          <td><div class="score-cell">${scorePill}${rerankerPill}</div></td>
          <td>${escapeHtml(r.brandName)}</td>
          <td>
            <div><strong>${escapeHtml(r.itemName)}</strong></div>
            <div class="muted" style="font-size:12px; max-width:520px;">${escapeHtml(r.description)}</div>
          </td>
          <td>${escapeHtml(r.classification)}</td>
          <td class="muted">${escapeHtml(r.supplier)}</td>
          <td class="muted">${escapeHtml(r.containerFullDescription)}</td>
        </tr>
      `;
      }).join("");
    }
    resultsEl.hidden = false;
  }

  function renderCompare(payload) {
    metaEl.textContent =
      `Query: "${payload.query}" · top ${payload.top} · ${payload.elapsed_ms} ms`;

    // Header: one column per pattern
    compareTheadEl.innerHTML = `
      <tr>
        <th class="compare-grid__rank">#</th>
        ${payload.panes.map((p) => `
          <th>
            <div><strong>${escapeHtml(p.label)}</strong></div>
            <div class="muted" style="font-weight: 400; font-size: 12px;">${escapeHtml(p.sub)}</div>
            <div class="muted" style="font-weight: 400; font-size: 11.5px;">
              ${p.error
                ? `<span class="compare-grid__err">${escapeHtml(p.error)}</span>`
                : `${p.results.length} result${p.results.length === 1 ? "" : "s"} · ${p.elapsed_ms} ms`}
            </div>
          </th>
        `).join("")}
      </tr>`;

    const maxRows = Math.max(0, ...payload.panes.map((p) => p.results.length));
    if (maxRows === 0) {
      compareTbodyEl.innerHTML = `
        <tr>
          <td colspan="${payload.panes.length + 1}" class="muted" style="text-align:center; padding:18px;">
            No matches across any pattern.
          </td>
        </tr>`;
    } else {
      const rows = [];
      for (let i = 0; i < maxRows; i++) {
        const cells = payload.panes.map((p) => {
          const r = p.results[i];
          if (!r) return `<td class="compare-grid__empty muted">—</td>`;
          const scorePill = `<span class="score-pill" title="@search.score">${r.score.toFixed(3)}</span>`;
          const rerankerPill = (r.reranker_score != null)
            ? ` <span class="score-pill score-pill--reranker" title="@search.rerankerScore">(${r.reranker_score.toFixed(3)})</span>`
            : "";
          return `
            <td class="compare-grid__cell" data-doc-id="${escapeHtml(r.id)}">
              <div class="score-cell" style="margin-bottom:6px;">${scorePill}${rerankerPill}</div>
              <div><strong>${escapeHtml(r.itemName)}</strong></div>
              <div class="muted" style="font-size:12px;">${escapeHtml(r.description)}</div>
              ${r.containerFullDescription ? `<div class="compare-grid__pack"><i class="fa-solid fa-box"></i> ${escapeHtml(r.containerFullDescription)}</div>` : ""}
            </td>`;
        }).join("");
        rows.push(`<tr><td class="compare-grid__rank muted">${i + 1}</td>${cells}</tr>`);
      }
      compareTbodyEl.innerHTML = rows.join("");
    }

    // Hover-highlight: show all cells with the same docId at once
    const cells = compareTbodyEl.querySelectorAll(".compare-grid__cell[data-doc-id]");
    cells.forEach((cell) => {
      cell.addEventListener("mouseenter", () => {
        const id = cell.dataset.docId;
        if (!id) return;
        compareTbodyEl.querySelectorAll(`.compare-grid__cell[data-doc-id="${CSS.escape(id)}"]`)
          .forEach((c) => c.classList.add("is-matched"));
      });
      cell.addEventListener("mouseleave", () => {
        compareTbodyEl.querySelectorAll(".compare-grid__cell.is-matched")
          .forEach((c) => c.classList.remove("is-matched"));
      });
    });

    compareEl.hidden = false;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const top = Math.max(1, Math.min(50, parseInt(fd.get("top"), 10) || 10));
    const query = String(fd.get("query") || "").trim();
    if (!query) { setStatus("Enter a query first.", "err"); return; }

    submitBtn.disabled = true;
    setStatus(MODE === "compare" ? "Running all patterns…" : "Running query…");

    try {
      let endpoint, body;
      if (MODE === "compare") {
        endpoint = `${API_BASE}/search/compare`;
        body = { query, top };
      } else {
        const pattern = String(fd.get("pattern") || "hybrid");
        body = { query, pattern, top };
        if (pattern === "filtered") {
          const f = String(fd.get("filter") || "").trim();
          if (f) body.filter = f;
        }
        endpoint = `${API_BASE}/search`;
      }

      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (res.status === 401) {
        setStatus("Not signed in. Click \"Sign in to Azure\" above.", "err");
        if (resultsEl) resultsEl.hidden = true;
        if (compareEl) compareEl.hidden = true;
        setAuthState("logged_out");
        return;
      }
      if (!res.ok) {
        const detail = (data && data.detail) || `HTTP ${res.status}`;
        setStatus(`Error: ${detail}`, "err");
        if (resultsEl) resultsEl.hidden = true;
        if (compareEl) compareEl.hidden = true;
        return;
      }
      if (MODE === "compare") {
        renderCompare(data);
      } else {
        renderResults(data);
      }
      setStatus(`Done in ${data.elapsed_ms} ms.`, "ok");
    } catch (err) {
      setStatus(`Network error: ${err.message || err}`, "err");
      if (resultsEl) resultsEl.hidden = true;
      if (compareEl) compareEl.hidden = true;
    } finally {
      submitBtn.disabled = false;
    }
  });
})();

// "Agent Integration Test" — chat panel that calls the Foundry agent
(function () {
  const root = document.getElementById("agent-tester");
  if (!root) return;

  // ---------- Auth (shared device-code flow with the search panel) --------
  const authBar       = root.querySelector("#agent-auth-bar");
  const authTitle     = root.querySelector("#agent-auth-bar__title");
  const authSubtitle  = root.querySelector("#agent-auth-bar__subtitle");
  const authLoginBtn  = root.querySelector("#agent-auth-bar__login");
  const authLogoutBtn = root.querySelector("#agent-auth-bar__logout");

  const authModal       = root.querySelector("#agent-auth-modal");
  const authModalCode   = root.querySelector("#agent-auth-modal__code");
  const authModalUrl    = root.querySelector("#agent-auth-modal__url");
  const authModalStatus = root.querySelector("#agent-auth-modal__status");
  const authModalCancel = root.querySelector("#agent-auth-modal__cancel");
  const authModalClose  = root.querySelector("#agent-auth-modal__close");

  const API_BASE  = (root.dataset.apiBase  || "/sections/ai_agent_integration/api").replace(/\/$/, "");
  const AUTH_BASE = (root.dataset.authBase || "/sections/index_retrieval_plan/api/auth").replace(/\/$/, "");

  let authState = "loading";
  let authPollTimer = null;
  let signedIn = false;

  // ---------- Chat UI -----------------------------------------------------
  const chatWindow   = root.querySelector("#agent-chat__window");
  const chatForm     = root.querySelector("#agent-chat__form");
  const chatInput    = root.querySelector("#agent-chat__input");
  const chatSend     = root.querySelector("#agent-chat__send");
  const chatReset    = root.querySelector("#agent-chat__reset");
  const chips        = root.querySelectorAll(".agent-chat__chip");

  let lastResponseId = null;
  let inFlight       = false;

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // Minimal, safe Markdown → HTML for agent responses.
  // Handles: fenced/inline code, **bold**, *italic*, _italic_, ~~strike~~,
  // [text](url), bullet/numbered lists, headings (###), blank-line paragraphs,
  // and line breaks. Always HTML-escapes first so nothing user-supplied is raw.
  function renderMarkdown(src) {
    if (!src) return "";
    const codeBlocks = [];
    const inlineCodes = [];

    // 1. Extract fenced code blocks ```lang\n...\n```
    let text = String(src).replace(/```([\w-]*)\n?([\s\S]*?)```/g, (_, lang, body) => {
      const i = codeBlocks.push({ lang, body }) - 1;
      return `\u0000CODEBLOCK${i}\u0000`;
    });

    // 2. Extract inline code `...`
    text = text.replace(/`([^`\n]+)`/g, (_, body) => {
      const i = inlineCodes.push(body) - 1;
      return `\u0000INLINECODE${i}\u0000`;
    });

    // 3. Escape everything else
    text = escapeHtml(text);

    // 4. Headings (###, ##, #) — at start of a line
    text = text.replace(/^######\s+(.+)$/gm, "<h6>$1</h6>");
    text = text.replace(/^#####\s+(.+)$/gm, "<h5>$1</h5>");
    text = text.replace(/^####\s+(.+)$/gm,  "<h4>$1</h4>");
    text = text.replace(/^###\s+(.+)$/gm,   "<h3>$1</h3>");
    text = text.replace(/^##\s+(.+)$/gm,    "<h2>$1</h2>");
    text = text.replace(/^#\s+(.+)$/gm,     "<h1>$1</h1>");

    // 5. Bold / italic / strike. Order matters — bold first.
    text = text.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
    text = text.replace(/__([^_\n]+)__/g,     "<strong>$1</strong>");
    text = text.replace(/(^|[\s(])\*([^*\n]+)\*/g, "$1<em>$2</em>");
    text = text.replace(/(^|[\s(])_([^_\n]+)_/g,   "$1<em>$2</em>");
    text = text.replace(/~~([^~\n]+)~~/g, "<del>$1</del>");

    // 6. Links [text](url) — only http/https/mailto
    text = text.replace(
      /\[([^\]]+)\]\(((?:https?:\/\/|mailto:)[^\s)]+)\)/g,
      (_, label, url) => `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`,
    );

    // 7. Lists. Group consecutive list lines, then wrap.
    const lines = text.split(/\n/);
    const out = [];
    let listType = null;          // "ul" | "ol" | null
    let listBuf = [];

    function flushList() {
      if (!listType) return;
      out.push(`<${listType}>${listBuf.join("")}</${listType}>`);
      listBuf = [];
      listType = null;
    }

    for (const raw of lines) {
      const ul = raw.match(/^\s*[-*+]\s+(.*)$/);
      const ol = raw.match(/^\s*\d+\.\s+(.*)$/);
      if (ul) {
        if (listType !== "ul") { flushList(); listType = "ul"; }
        listBuf.push(`<li>${ul[1]}</li>`);
      } else if (ol) {
        if (listType !== "ol") { flushList(); listType = "ol"; }
        listBuf.push(`<li>${ol[1]}</li>`);
      } else {
        flushList();
        out.push(raw);
      }
    }
    flushList();
    text = out.join("\n");

    // 8. Paragraphs from blank-line gaps. Skip blocks already wrapped.
    const blockOpen = /^\s*<(?:h\d|ul|ol|li|pre|blockquote|table)\b/i;
    text = text
      .split(/\n{2,}/)
      .map((para) => {
        const trimmed = para.trim();
        if (!trimmed) return "";
        if (blockOpen.test(trimmed)) return trimmed;
        return `<p>${trimmed.replace(/\n/g, "<br>")}</p>`;
      })
      .filter(Boolean)
      .join("");

    // 9. Restore inline code, then fenced code blocks
    text = text.replace(/\u0000INLINECODE(\d+)\u0000/g,
      (_, i) => `<code>${escapeHtml(inlineCodes[+i])}</code>`);
    text = text.replace(/\u0000CODEBLOCK(\d+)\u0000/g, (_, i) => {
      const { body } = codeBlocks[+i];
      return `<pre><code>${escapeHtml(body.replace(/\n$/, ""))}</code></pre>`;
    });

    return text;
  }

  function setEmptyState() {
    chatWindow.innerHTML = `
      <div class="agent-chat__empty">
        <i class="fa-solid fa-wand-magic-sparkles"></i>
        Ask <strong>search-workshop-demo</strong> a beverage-catalog question.<br>
        Replies are grounded in the <code>beverage-catalog</code> index.
      </div>`;
  }

  function appendMessage({ role, text, meta, sources, error }) {
    // Drop the empty-state placeholder
    const empty = chatWindow.querySelector(".agent-chat__empty");
    if (empty) empty.remove();

    const wrap = document.createElement("div");
    wrap.className = `agent-msg agent-msg--${role}` + (error ? " agent-msg--error" : "");

    const avatar = document.createElement("div");
    avatar.className = "agent-msg__avatar";
    avatar.innerHTML = role === "user"
      ? '<i class="fa-solid fa-user"></i>'
      : (error ? '<i class="fa-solid fa-circle-exclamation"></i>' : '<i class="fa-solid fa-robot"></i>');
    wrap.appendChild(avatar);

    const bubble = document.createElement("div");
    bubble.className = "agent-msg__bubble";
    if (role === "assistant" && !error) {
      // Render markdown (bold, italic, code, lists, links). HTML-escapes first.
      bubble.innerHTML = renderMarkdown(text);
    } else {
      bubble.textContent = text || "";
    }

    if (meta) {
      const metaEl = document.createElement("div");
      metaEl.className = "agent-msg__meta";
      metaEl.innerHTML = meta;
      bubble.appendChild(metaEl);
    }

    // Stack container so bubble + product panel sit in a column next to the avatar.
    const stack = document.createElement("div");
    stack.className = "agent-msg__stack";
    stack.appendChild(bubble);

    // Product suggestions — rendered as a separate panel below the bubble so
    // they don't visually compete with the agent's prose.
    if (sources && sources.length) {
      const panel = document.createElement("div");
      panel.className = "agent-products";

      const heading = document.createElement("div");
      heading.className = "agent-products__title";
      heading.innerHTML = `
        <i class="fa-solid fa-wine-bottle"></i>
        <span>Here are your product suggestions</span>
        <span class="agent-products__count">${sources.length}</span>`;
      panel.appendChild(heading);

      const grid = document.createElement("div");
      grid.className = "agent-products__grid";

      sources.forEach((d) => {
        const card = document.createElement("article");
        card.className = "agent-product";

        const id = String(d.id || "");
        const imgUrl = id ? `/static/images/${encodeURIComponent(id)}.png` : "";
        const initial = (d.brandName || d.itemName || "·").trim().charAt(0).toUpperCase();

        const subline = [d.brandName, d.container].filter(Boolean).map(escapeHtml).join(" · ");
        const scorePill = (typeof d.score === "number" && d.score > 0)
          ? `<span class="agent-product__score" title="@search.score">${d.score.toFixed(3)}</span>`
          : "";

        card.innerHTML = `
          <div class="agent-product__media">
            ${imgUrl
              ? `<img class="agent-product__img"
                      src="${imgUrl}"
                      alt="${escapeHtml(d.itemName || d.brandName || id)}"
                      loading="lazy"
                      onerror="this.closest('.agent-product__media').classList.add('agent-product__media--missing'); this.remove();">`
              : ""}
            <span class="agent-product__placeholder" aria-hidden="true">${escapeHtml(initial)}</span>
          </div>
          <div class="agent-product__body">
            <div class="agent-product__row">
              <h4 class="agent-product__name">${escapeHtml(d.itemName || d.brandName || id)}</h4>
              ${scorePill}
            </div>
            ${subline ? `<div class="agent-product__sub muted">${subline}</div>` : ""}
            ${d.description ? `<p class="agent-product__desc">${escapeHtml(d.description)}</p>` : ""}
          </div>`;

        grid.appendChild(card);
      });

      panel.appendChild(grid);
      stack.appendChild(panel);
    }

    wrap.appendChild(stack);
    chatWindow.appendChild(wrap);

    // Scroll positioning:
    //  - User messages & errors: scroll to the bottom so the input + typing
    //    indicator stay in view.
    //  - Assistant replies: anchor the top of the message at the top of the
    //    chat window so the user reads the answer first; the product cards
    //    below remain reachable by scrolling.
    if (role === "assistant" && !error) {
      const top = wrap.offsetTop - chatWindow.offsetTop;
      chatWindow.scrollTo({ top: Math.max(0, top - 4), behavior: "smooth" });
    } else {
      chatWindow.scrollTop = chatWindow.scrollHeight;
    }
    return wrap;
  }

  function appendTyping() {
    const wrap = document.createElement("div");
    wrap.className = "agent-msg agent-msg--assistant agent-msg--typing";
    wrap.innerHTML = `
      <div class="agent-msg__avatar"><i class="fa-solid fa-robot"></i></div>
      <div class="agent-msg__bubble">
        <span class="agent-msg__dot"></span>
        <span class="agent-msg__dot"></span>
        <span class="agent-msg__dot"></span>
      </div>`;
    chatWindow.appendChild(wrap);
    chatWindow.scrollTop = chatWindow.scrollHeight;
    return wrap;
  }

  function autosize() {
    chatInput.style.height = "auto";
    chatInput.style.height = Math.min(180, chatInput.scrollHeight) + "px";
  }

  function updateSendEnabled() {
    chatSend.disabled = inFlight || !signedIn || !chatInput.value.trim();
  }

  // ---------- Auth helpers (mirrors search-tester) ------------------------
  function setAuthState(state, payload) {
    authState = state;
    authBar.dataset.status = state === "pending" ? "logged_out" : state;
    if (state === "ok") {
      const acc = payload && payload.account;
      authTitle.textContent = "Signed in to Azure";
      authSubtitle.textContent = acc
        ? `${acc.user || "(unknown user)"} · ${acc.subscription_name || acc.subscription_id || ""}`
        : "Agent calls are enabled.";
      authLoginBtn.hidden = true;
      authLogoutBtn.hidden = false;
      signedIn = true;
    } else if (state === "logged_out") {
      authTitle.textContent = "Not signed in";
      authSubtitle.textContent = "Sign in with Entra to call the Foundry agent.";
      authLoginBtn.hidden = false;
      authLogoutBtn.hidden = true;
      signedIn = false;
    } else if (state === "pending") {
      authTitle.textContent = "Sign-in pending…";
      authSubtitle.textContent = "Complete the device-code flow in your browser.";
      authLoginBtn.hidden = false; authLoginBtn.disabled = true;
      authLogoutBtn.hidden = true;
      signedIn = false;
    } else if (state === "error") {
      authTitle.textContent = "Sign-in failed";
      authSubtitle.textContent = (payload && payload.error) || "Try signing in again.";
      authLoginBtn.hidden = false; authLoginBtn.disabled = false;
      authLogoutBtn.hidden = true;
      signedIn = false;
    } else {
      authTitle.textContent = "Checking sign-in…";
      authSubtitle.textContent = "";
      authLoginBtn.hidden = true; authLogoutBtn.hidden = true;
      signedIn = false;
    }
    chatInput.disabled = !signedIn;
    updateSendEnabled();
  }

  function openAuthModal(code, url) {
    authModalCode.textContent = code || "—";
    if (url) {
      authModalUrl.textContent = url;
      authModalUrl.href = url;
    }
    authModalStatus.classList.remove("auth-modal__status--err");
    authModalStatus.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Waiting for you to complete sign-in…';
    authModal.hidden = false;
  }

  function closeAuthModal() {
    authModal.hidden = true;
    if (authPollTimer) { clearInterval(authPollTimer); authPollTimer = null; }
    authLoginBtn.disabled = false;
  }

  async function refreshAuthStatus() {
    try {
      const res = await fetch(`${AUTH_BASE}/status`);
      const data = await res.json().catch(() => ({}));
      if (data.status === "ok") {
        setAuthState("ok", data);
        if (!authModal.hidden) {
          authModalStatus.innerHTML = '<i class="fa-solid fa-circle-check"></i> Signed in. Closing…';
          setTimeout(closeAuthModal, 700);
        }
        return data;
      }
      if (data.status === "pending") { setAuthState("pending", data); return data; }
      if (data.error) { setAuthState("error", data); return data; }
      setAuthState("logged_out");
      return data;
    } catch (err) {
      setAuthState("error", { error: err.message || String(err) });
      return null;
    }
  }

  authLoginBtn.addEventListener("click", async () => {
    authLoginBtn.disabled = true;
    setAuthState("pending");
    try {
      const res = await fetch(`${AUTH_BASE}/login`, { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) { setAuthState("error", { error: data.detail || `HTTP ${res.status}` }); return; }
      if (data.status === "ok") { setAuthState("ok", data); return; }
      openAuthModal(data.device_code, data.url);
      if (authPollTimer) clearInterval(authPollTimer);
      authPollTimer = setInterval(() => {
        refreshAuthStatus().then((d) => {
          if (d && d.status === "ok") {
            clearInterval(authPollTimer); authPollTimer = null;
          } else if (d && d.status === "logged_out" && d.error) {
            authModalStatus.classList.add("auth-modal__status--err");
            authModalStatus.textContent = "Sign-in failed: " + d.error;
            clearInterval(authPollTimer); authPollTimer = null;
          }
        });
      }, 3000);
    } catch (err) {
      setAuthState("error", { error: err.message || String(err) });
    }
  });

  authLogoutBtn.addEventListener("click", async () => {
    authLogoutBtn.disabled = true;
    try { await fetch(`${AUTH_BASE}/logout`, { method: "POST" }); }
    finally { authLogoutBtn.disabled = false; setAuthState("logged_out"); }
  });

  authModalCancel.addEventListener("click", closeAuthModal);
  authModalClose.addEventListener("click", closeAuthModal);
  authModal.addEventListener("click", (e) => { if (e.target === authModal) closeAuthModal(); });

  root.querySelectorAll("[data-copy]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const target = root.querySelector("#" + btn.dataset.copy);
      const text = target ? (target.textContent || target.value || "").trim() : "";
      if (!text) return;
      try {
        await navigator.clipboard.writeText(text);
        const orig = btn.innerHTML;
        btn.innerHTML = '<i class="fa-solid fa-check"></i> Copied';
        setTimeout(() => { btn.innerHTML = orig; }, 1200);
      } catch (_) {}
    });
  });

  // ---------- Send / receive ---------------------------------------------
  async function sendMessage(text) {
    const message = String(text || "").trim();
    if (!message || inFlight || !signedIn) return;

    appendMessage({ role: "user", text: message });
    chatInput.value = "";
    autosize();

    inFlight = true;
    updateSendEnabled();
    const typing = appendTyping();

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          previous_response_id: lastResponseId,
        }),
      });
      const data = await res.json().catch(() => ({}));
      typing.remove();

      if (res.status === 401) {
        appendMessage({
          role: "assistant",
          text: "Not signed in. Use \"Sign in to Azure\" above and try again.",
          error: true,
        });
        setAuthState("logged_out");
        return;
      }
      if (!res.ok) {
        const detail = (data && data.detail) || `HTTP ${res.status}`;
        appendMessage({ role: "assistant", text: `Error: ${detail}`, error: true });
        return;
      }

      lastResponseId = data.response_id || lastResponseId;
      const meta = `<span><i class="fa-solid fa-stopwatch"></i>${data.elapsed_ms} ms</span>`
                 + `<span><i class="fa-solid fa-robot"></i>${escapeHtml(data.agent || "agent")}</span>`;
      appendMessage({
        role: "assistant",
        text: data.answer || "(empty response)",
        meta,
        sources: data.documents,
      });
    } catch (err) {
      typing.remove();
      appendMessage({
        role: "assistant",
        text: `Network error: ${err.message || err}`,
        error: true,
      });
    } finally {
      inFlight = false;
      updateSendEnabled();
    }
  }

  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    sendMessage(chatInput.value);
  });

  chatInput.addEventListener("input", () => { autosize(); updateSendEnabled(); });
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(chatInput.value);
    }
  });

  chips.forEach((b) => {
    b.addEventListener("click", () => {
      const p = b.dataset.prompt || b.textContent.trim();
      if (!signedIn) {
        chatInput.value = p;
        autosize();
        updateSendEnabled();
        return;
      }
      sendMessage(p);
    });
  });

  chatReset.addEventListener("click", () => {
    lastResponseId = null;
    setEmptyState();
  });

  setEmptyState();
  refreshAuthStatus();
})();


// =====================================================================
// Demo mode toggle (Real / Mock) — sidebar footer
// Persists choice via cookie `demo_mode` (set server-side).
// =====================================================================
(function () {
  const root = document.querySelector('.demo-toggle');
  if (!root) return;
  const buttons = root.querySelectorAll('.demo-toggle__btn');
  buttons.forEach((btn) => {
    btn.addEventListener('click', async () => {
      const mode = btn.dataset.set;
      if (root.dataset.mode === mode) return;
      buttons.forEach((b) => (b.disabled = true));
      try {
        const res = await fetch('/api/demo-mode', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode }),
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        root.dataset.mode = data.mode;
        // Reload so all section pages re-render with the new mode.
        window.location.reload();
      } catch (err) {
        console.error('demo-mode toggle failed', err);
        buttons.forEach((b) => (b.disabled = false));
      }
    });
  });
})();


// =====================================================================
// Industry selector — sidebar footer
// Persists choice via cookie `industry` (set server-side) and reloads
// so all section pages re-render with the new pack.
// =====================================================================
(function () {
  const select = document.getElementById('industry-select');
  if (!select) return;
  select.addEventListener('change', async () => {
    const slug = select.value;
    if (!slug || slug === select.dataset.current) return;
    select.disabled = true;
    try {
      const res = await fetch('/api/industry', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ industry: slug }),
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      window.location.reload();
    } catch (err) {
      console.error('industry change failed', err);
      select.value = select.dataset.current;
      select.disabled = false;
    }
  });
})();


// =====================================================================
// Language selector — sidebar footer
// Persists choice via cookie `lang` and reloads to re-render UI chrome.
// =====================================================================
(function () {
  const select = document.getElementById('language-select');
  if (!select) return;
  select.addEventListener('change', async () => {
    const code = select.value;
    if (!code || code === select.dataset.current) return;
    select.disabled = true;
    try {
      const res = await fetch('/api/language', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ language: code }),
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      window.location.reload();
    } catch (err) {
      console.error('language change failed', err);
      select.value = select.dataset.current;
      select.disabled = false;
    }
  });
})();


// =====================================================================
// Azure / Foundry connection status (sidebar footer)
// =====================================================================
(function () {
  const root = document.getElementById('az-status');
  if (!root) return;
  const userEl = root.querySelector('[data-field="azure"]');
  const azPill = root.querySelector('[data-field="azure-pill"]');
  const fdPill = root.querySelector('[data-field="foundry-pill"]');
  const loginBtn = document.getElementById('az-login-btn');
  const logoutBtn = document.getElementById('az-logout-btn');
  const deviceBox = document.getElementById('az-device');
  const deviceUrl = document.getElementById('az-device-url');
  const deviceCode = document.getElementById('az-device-code');

  function setPill(el, state, label, tip) {
    if (!el) return;
    el.dataset.state = state;
    el.title = tip || label;
  }

  async function refresh() {
    try {
      const res = await fetch('/api/azure-status');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      root.dataset.state = data.state || 'error';
      const az = data.azure || {};
      const fd = data.foundry || {};

      setPill(azPill, az.ok ? 'ok' : 'error',
              'Azure', az.user || az.error || 'desconectado');
      const fdState = fd.ok ? 'ok' : (fd.endpoint ? (az.ok ? 'error' : 'degraded') : 'degraded');
      setPill(fdPill, fdState,
              'Foundry', fd.project || fd.endpoint || fd.error || 'não configurado');

      if (az.ok) {
        userEl.textContent = az.user || 'conectado';
        userEl.title = az.user || '';
        loginBtn.hidden = true;
        logoutBtn.hidden = false;
      } else {
        userEl.textContent = '';
        userEl.title = '';
        loginBtn.hidden = false;
        logoutBtn.hidden = true;
      }
    } catch (err) {
      root.dataset.state = 'error';
      setPill(azPill, 'error', 'Azure', 'erro');
      setPill(fdPill, 'error', 'Foundry', '—');
      userEl.textContent = '';
      loginBtn.hidden = false;
      logoutBtn.hidden = true;
    }
  }

  async function pollLogin() {
    try {
      const res = await fetch('/api/azure-login');
      if (!res.ok) return;
      const data = await res.json();
      if (data.code) {
        deviceBox.hidden = false;
        deviceCode.textContent = data.code;
        deviceUrl.href = data.url || 'https://login.microsoft.com/device';
        deviceUrl.textContent = (data.url || 'login.microsoft.com/device').replace(/^https?:\/\//, '');
      }
      if (data.running) {
        setTimeout(pollLogin, 2500);
      } else {
        await refresh();
        if (root.dataset.state === 'ok' || root.dataset.state === 'degraded') {
          deviceBox.hidden = true;
        }
      }
    } catch (e) { /* swallow */ }
  }

  loginBtn.addEventListener('click', async () => {
    loginBtn.disabled = true;
    deviceBox.hidden = false;
    deviceCode.textContent = 'iniciando…';
    try {
      const res = await fetch('/api/azure-login', { method: 'POST' });
      const data = await res.json();
      if (data.code) {
        deviceCode.textContent = data.code;
        deviceUrl.href = data.url || 'https://login.microsoft.com/device';
        deviceUrl.textContent = (data.url || 'login.microsoft.com/device').replace(/^https?:\/\//, '');
      }
      pollLogin();
    } catch (err) {
      deviceCode.textContent = 'erro';
    } finally {
      loginBtn.disabled = false;
    }
  });

  logoutBtn.addEventListener('click', async () => {
    if (!confirm('Sair da sessão do Azure dentro do container?')) return;
    logoutBtn.disabled = true;
    try {
      await fetch('/api/azure-logout', { method: 'POST' });
      deviceBox.hidden = true;
      await refresh();
    } catch (err) { /* swallow */ }
    finally { logoutBtn.disabled = false; }
  });

  refresh();
  // Periodic refresh every 30s
  setInterval(refresh, 30000);
})();
