/* ===== Knockout brackets: view for everyone, inline editing for admins =====
 *
 * Loaded after game.js and reuses its globals ($, csrf, showToast, switchView,
 * toFa). Same freshness model as the inbox: no realtime, an explicit Refresh
 * button, a visible "updated N minutes ago", and a cheap refetch when the tab
 * comes back into view.
 *
 * Who stands in a later-round match is derived here exactly as bracket.py
 * derives it on the server -- by following winners forward from the draw. The
 * server is the authority (every edit is a PATCH whose response replaces local
 * state), this copy only exists so the page can paint without a round trip.
 *
 * There are two independent draws -- boys and girls. Each keeps its own state
 * (data, freshness, edit mode) in bk.views; only the selected one is on
 * screen, and the other is not even fetched until its tab is first opened.
 */
(function () {
  "use strict";

  const byId = (id) => document.getElementById(id);
  const toast = (text, kind) =>
    typeof showToast === "function" ? showToast(text, kind) : console.log(text);
  const faDigits = (value) => (typeof toFa === "function" ? toFa(value) : String(value));
  const esc = (value) =>
    String(value == null ? "" : value).replace(
      /[&<>"']/g,
      (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );

  const SIZES = [2, 4, 8, 16, 32, 64];
  const ROUND_NAMES = {
    2: "فینال",
    4: "نیمه‌نهایی",
    8: "یک‌چهارم نهایی",
    16: "یک‌هشتم نهایی",
    32: "یک‌شانزدهم نهایی",
    64: "یک‌سی‌ودوم نهایی",
  };
  const MIN_AUTO_REFETCH_MS = 20000;
  const ZOOM_STEPS = [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1];

  const DIVISIONS = ["boys", "girls"];

  // One of these per division; only the selected one is ever rendered.
  const newView = () => ({
    data: null,
    fetchedAt: null,
    loading: false,
    loadedOnce: false,
    error: null,
    editing: false,
  });

  const bk = {
    division: "boys",
    views: { boys: newView(), girls: newView() },
    zoom: 1,
    saving: 0,
    savedTimer: null,
  };

  // The state of the division on screen -- or of a named one, for a fetch
  // still in flight after the user has moved to the other tab.
  const S = (division) => bk.views[division || bk.division];

  /* ------------------------------------------------------------- plumbing */

  async function api(url, { method = "GET", body } = {}) {
    let response;
    const options = { method, headers: { "X-CSRFToken": csrf } };
    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    try {
      response = await fetch(url, options);
    } catch (e) {
      throw new Error("ارتباط با سرور برقرار نشد. اتصال را بررسی کن و دوباره تلاش کن.");
    }
    if (response.status === 401) {
      if (typeof handleAuthExpired === "function") handleAuthExpired();
      throw new Error("نشست تو به پایان رسیده است. دوباره وارد شو.");
    }
    let data = null;
    try {
      data = await response.json();
    } catch (e) {
      if (response.ok) throw new Error("پاسخ سرور خوانده نشد.");
    }
    if (!response.ok) throw new Error((data && data.error) || "خطای سرور (" + response.status + ").");
    return data;
  }

  const dateFmt = new Intl.DateTimeFormat("fa-IR", { dateStyle: "medium" });
  function relTime(iso) {
    if (!iso) return "";
    const then = new Date(iso).getTime();
    if (!isFinite(then)) return "";
    const seconds = Math.round((Date.now() - then) / 1000);
    if (seconds < 45) return "همین حالا";
    const minutes = Math.round(seconds / 60);
    if (minutes < 60) return faDigits(minutes) + " دقیقه پیش";
    const hours = Math.round(minutes / 60);
    if (hours < 24) return faDigits(hours) + " ساعت پیش";
    const days = Math.round(hours / 24);
    if (days < 7) return faDigits(days) + " روز پیش";
    return dateFmt.format(new Date(iso));
  }

  /* ----------------------------------------------------------- derivation */

  const rounds = () => Math.log2(S().data.size);
  const matchesIn = (r) => S().data.size >> (r + 1);
  const key = (r, i) => r + "-" + i;

  function decided(k) {
    const entry = S().data.results[k];
    return entry && (entry.winner === 0 || entry.winner === 1) ? entry.winner : null;
  }
  function scoreOf(k) {
    const entry = S().data.results[k];
    return entry && Array.isArray(entry.score) ? entry.score : null;
  }
  function participants(r, i) {
    if (r === 0) return [S().data.teams[2 * i] || null, S().data.teams[2 * i + 1] || null];
    return [winnerName(r - 1, 2 * i), winnerName(r - 1, 2 * i + 1)];
  }
  function winnerName(r, i) {
    const side = decided(key(r, i));
    return side === null ? null : participants(r, i)[side];
  }
  function loserName(r, i) {
    const side = decided(key(r, i));
    return side === null ? null : participants(r, i)[1 - side];
  }
  function thirdParticipants() {
    const R = rounds();
    if (R < 2) return [null, null];
    return [loserName(R - 2, 0), loserName(R - 2, 1)];
  }
  // The matches the champion won, so their connectors can be lit in gold.
  function championPath() {
    const path = new Set();
    let r = rounds() - 1;
    let i = 0;
    while (r >= 0) {
      const side = decided(key(r, i));
      if (side === null) break;
      path.add(key(r, i));
      i = 2 * i + side;
      r -= 1;
    }
    return path;
  }

  // Column order across the stage: first half of the draw running in from
  // the start edge, the final in the middle, second half running in from the
  // end edge. Match (r, i) belongs to the first half when i is in the lower
  // half of its round.
  function columns() {
    const R = rounds();
    const cols = [];
    for (let r = 0; r < R - 1; r++) cols.push({ r, side: 0 });
    cols.push({ r: R - 1, side: "final" });
    for (let r = R - 2; r >= 0; r--) cols.push({ r, side: 1 });
    return cols;
  }
  function matchesFor(col) {
    const count = matchesIn(col.r);
    if (col.side === "final") return [0];
    const half = count / 2;
    const out = [];
    for (let i = col.side === 0 ? 0 : half; i < (col.side === 0 ? half : count); i++) out.push(i);
    return out;
  }

  /* ------------------------------------------------------------ rendering */

  function hue(name) {
    let h = 0;
    for (const ch of String(name)) h = (h * 31 + ch.codePointAt(0)) % 360;
    return h;
  }

  function rowHTML(k, side, name, score, winner, editable, isFinal) {
    const state =
      name === null ? "empty" : winner === null ? "" : winner === side ? "win" : "lose";
    const shown = name === null ? "در انتظار…" : name;
    const initial = name ? [...name.trim()][0] : "؟";
    const ava =
      '<span class="bk-ava" style="--h:' + (name ? hue(name) : 200) + '" aria-hidden="true">' +
      esc(initial) +
      "</span>";

    let nameHTML;
    const teamIdx = k.startsWith("0-") ? 2 * parseInt(k.slice(2), 10) + side : null;
    if (editable && teamIdx !== null) {
      nameHTML =
        '<input class="bk-name-input" list="bkTeamSuggest" maxlength="40" data-team="' +
        teamIdx +
        '" value="' +
        esc(name || "") +
        '" placeholder="نام تیم ' +
        faDigits(teamIdx + 1) +
        '" aria-label="نام تیم جایگاه ' +
        faDigits(teamIdx + 1) +
        '">';
    } else {
      nameHTML = '<span class="bk-name">' + esc(shown) + "</span>";
    }

    const bothKnown = editable && name !== null && !k.startsWith("__");
    let tail = "";
    if (editable && bothKnown) {
      tail +=
        '<input class="bk-score-input" type="number" min="0" max="99" inputmode="numeric" data-key="' +
        k +
        '" data-side="' +
        side +
        '" value="' +
        (score ? score[side] : "") +
        '" aria-label="گل‌های ' +
        esc(name) +
        '">';
      tail +=
        '<button type="button" class="bk-win" data-key="' +
        k +
        '" data-side="' +
        side +
        '" aria-pressed="' +
        (winner === side) +
        '" title="برنده: ' +
        esc(name) +
        '">✓</button>';
    } else {
      tail +=
        '<span class="bk-score' +
        (score ? "" : " blank") +
        '">' +
        (score ? faDigits(score[side]) : "–") +
        "</span>";
    }
    return '<div class="bk-row ' + state + '">' + ava + nameHTML + tail + "</div>";
  }

  function matchHTML(k, sides, extraClass, label) {
    const editable = S().editing && S().data.can_edit;
    const winner = decided(k);
    const score = scoreOf(k);
    const bothKnown = sides[0] !== null && sides[1] !== null;
    const isFinal = extraClass.includes("is-final");
    // Winner buttons only make sense once both sides exist; inputs for names
    // stay available regardless so the draw can be typed in.
    const rowEditable = editable && (k.startsWith("0-") || bothKnown);
    const rows =
      rowHTML(k, 0, sides[0], score, winner, rowEditable && (bothKnown || k.startsWith("0-")), isFinal) +
      rowHTML(k, 1, sides[1], score, winner, rowEditable && (bothKnown || k.startsWith("0-")), isFinal);
    const clear =
      editable && (winner !== null || score)
        ? '<button type="button" class="bk-clear" data-clear="' + k + '" title="پاک کردن نتیجه">✕</button>'
        : "";
    const tag = editable && label ? '<span class="bk-tag">' + esc(label) + "</span>" : "";
    return (
      '<div class="bk-match ' +
      extraClass +
      (winner !== null ? " is-done" : "") +
      '" data-key="' +
      k +
      '">' +
      tag +
      clear +
      rows +
      "</div>"
    );
  }

  function skeletonHTML() {
    return '<div class="bk-skel"></div>';
  }

  function emptyHTML(icon, text) {
    return '<div class="bk-empty"><span class="ico" aria-hidden="true">' + icon + "</span>" + text + "</div>";
  }

  function render() {
    const stageWrap = byId("bkStageWrap");
    const champ = byId("bkChampion");
    if (!stageWrap) return;

    paintDivisionTabs();

    byId("bkUpdated").textContent = S().fetchedAt
      ? "به‌روزرسانی: " + relTime(S().fetchedAt.toISOString())
      : "هنوز به‌روزرسانی نشده";

    if (!S().data) {
      champ.hidden = true;
      stageWrap.innerHTML = S().loading ? skeletonHTML() : S().error
        ? emptyHTML("⚠️", "جدول بارگذاری نشد.<br>دکمهٔ «تازه‌سازی» را بزن.")
        : "";
      byId("bkAdmin").hidden = true;
      return;
    }

    const d = S().data;
    byId("bkTitle").textContent = d.title || "جدول حذفی";
    const meta = [];
    if (d.size) meta.push(faDigits(d.size) + " تیم");
    if (d.updated_by) meta.push("آخرین ویرایش: " + d.updated_by + (d.updated_at ? " · " + relTime(d.updated_at) : ""));
    if (d.can_edit && !d.published) meta.push("پیش‌نویس — کاربران هنوز نمی‌بینند");
    byId("bkMeta").textContent = meta.join("  ·  ");

    paintAdminBar();

    if (!d.published && !d.can_edit) {
      champ.hidden = true;
      stageWrap.innerHTML = emptyHTML("🏆", "جدول حذفی هنوز منتشر نشده است.<br>وقتی مدیر جدول را آماده کند اینجا نمایش داده می‌شود.");
      return;
    }

    // Champion banner: always present so the bracket has a summit to look at.
    champ.hidden = false;
    champ.className = "bk-champ" + (d.champion ? "" : " pending");
    champ.innerHTML =
      '<span class="bk-trophy" aria-hidden="true">🏆</span><div><small>' +
      (d.champion ? "قهرمان" : "قهرمان هنوز مشخص نشده") +
      "</small><b>" +
      esc(d.champion || (d.title || "جدول حذفی")) +
      "</b></div>";

    const cols = columns();
    const R = rounds();
    const path = championPath();
    const finalCol = cols.findIndex((c) => c.side === "final") + 1;

    let head = "";
    let grid = '<svg class="bk-lines" aria-hidden="true"></svg>';
    cols.forEach((col) => {
      const teamsInRound = d.size >> col.r;
      const label = ROUND_NAMES[teamsInRound] || "دور " + faDigits(col.r + 1);
      const count = matchesFor(col).length;
      head +=
        '<div class="bk-rh' +
        (col.side === "final" ? " final" : "") +
        '"><b>' +
        (col.side === "final" ? "🏆 " : "") +
        esc(label) +
        "</b><small>" +
        (col.side === "final" ? "بازی نهایی" : faDigits(count) + " بازی") +
        "</small></div>";
      grid += '<div class="bk-col">';
      matchesFor(col).forEach((i) => {
        const k = key(col.r, i);
        const cls = (col.side === "final" ? "is-final" : "") + (path.has(k) ? " on-path" : "");
        grid += matchHTML(k, participants(col.r, i), cls, "بازی " + faDigits(i + 1));
      });
      grid += "</div>";
    });

    let foot = "";
    if (R >= 2) {
      const third = thirdParticipants();
      foot =
        '<div class="bk-foot" style="--cols:' + cols.length + '">' +
        '<div class="bk-third-wrap" style="grid-column:' + finalCol + '">' +
        '<div class="bk-third-label">🥉 بازی رده‌بندی' +
        (d.third_place ? " — مقام سوم: " + esc(d.third_place) : "") +
        "</div>" +
        matchHTML("third", third, "is-third", "رده‌بندی") +
        "</div></div>";
    }

    const focus = captureFocus();
    stageWrap.innerHTML =
      '<div class="bk-scroll" id="bkScroll"><div class="bk-zoomwrap" id="bkZoomWrap">' +
      '<div class="bk-stage' + (S().editing && d.can_edit ? " bk-editing" : "") + '" id="bkStage" style="--cols:' + cols.length + '">' +
      '<div class="bk-head">' + head + "</div>" +
      '<div class="bk-grid" id="bkGrid">' + grid + "</div>" +
      foot +
      "</div></div></div>";
    restoreFocus(focus);
    drawLines();
    applyZoom();
  }

  /* ------------------------------------------------------ division tabs */

  // The hint under a tab: enough to tell the two draws apart without opening
  // both -- the champion once there is one, otherwise where the draw stands.
  function tabHint(division) {
    const view = S(division);
    const d = view.data;
    if (!d) return view.loading ? "در حال بارگذاری…" : view.error ? "بارگذاری نشد" : "";
    if (d.champion) return "🏆 " + d.champion;
    if (!d.published) return d.can_edit ? "پیش‌نویس" : "منتشر نشده";
    return d.size ? faDigits(d.size) + " تیم" : "";
  }

  function paintDivisionTabs() {
    DIVISIONS.forEach((division) => {
      const btn = document.querySelector('.bk-div-tab[data-division="' + division + '"]');
      if (!btn) return;
      const active = division === bk.division;
      btn.classList.toggle("on", active);
      btn.setAttribute("aria-selected", String(active));
      btn.tabIndex = active ? 0 : -1;
      const hint = btn.querySelector(".bk-div-hint");
      if (hint) hint.textContent = tabHint(division);
    });
  }

  function switchDivision(division) {
    if (!bk.views[division] || division === bk.division) return;
    bk.division = division;
    render();
    paintRefresh();
    // Each draw is fetched only when someone actually opens it.
    load({ quiet: true, auto: true });
    requestAnimationFrame(() => {
      drawLines();
      applyZoom();
    });
  }

  function paintAdminBar() {
    const bar = byId("bkAdmin");
    const d = S().data;
    if (!bar) return;
    bar.hidden = !(d && d.can_edit);
    if (bar.hidden) return;
    const editBtn = byId("bkEditToggle");
    editBtn.classList.toggle("on", S().editing);
    editBtn.textContent = S().editing ? "✅ پایان ویرایش" : "✏️ ویرایش جدول";
    byId("bkEditTools").hidden = !S().editing;
    if (document.activeElement !== byId("bkTitleInput")) byId("bkTitleInput").value = d.title || "";
    byId("bkSizeSelect").value = String(d.size);
    byId("bkPublished").checked = !!d.published;
    const list = byId("bkTeamSuggest");
    if (list) list.innerHTML = (d.suggestions || []).map((u) => '<option value="' + esc(u) + '">').join("");
  }

  /* ---------------------------------------------------- connector lines */

  function drawLines() {
    const grid = byId("bkGrid");
    const svg = grid && grid.querySelector(".bk-lines");
    if (!grid || !svg || !S().data) return;
    const R = rounds();
    const path = championPath();
    const w = grid.scrollWidth;
    const h = grid.scrollHeight;
    svg.setAttribute("viewBox", "0 0 " + w + " " + h);
    svg.setAttribute("width", w);
    svg.setAttribute("height", h);

    const box = (el) => ({
      left: el.offsetLeft,
      top: el.offsetTop,
      right: el.offsetLeft + el.offsetWidth,
      cy: el.offsetTop + el.offsetHeight / 2,
      cx: el.offsetLeft + el.offsetWidth / 2,
    });

    let paths = "";
    grid.querySelectorAll(".bk-match[data-key]").forEach((el) => {
      const k = el.dataset.key;
      const m = /^(\d+)-(\d+)$/.exec(k);
      if (!m) return;
      const r = parseInt(m[1], 10);
      const i = parseInt(m[2], 10);
      if (r >= R - 1) return;
      const target = grid.querySelector('.bk-match[data-key="' + key(r + 1, Math.floor(i / 2)) + '"]');
      if (!target) return;
      const a = box(el);
      const b = box(target);
      // Leave from whichever edge faces the next round, arrive on the far side.
      const toStart = b.cx < a.cx;
      const sx = toStart ? a.left : a.right;
      const ex = toStart ? b.right : b.left;
      const mx = (sx + ex) / 2;
      const cls = path.has(k) ? "is-champ" : decided(k) !== null ? "is-adv" : "";
      paths +=
        '<path class="' + cls + '" d="M' + sx + " " + a.cy + " H" + mx + " V" + b.cy + " H" + ex + '"/>';
    });
    svg.innerHTML = paths;
  }

  /* ------------------------------------------------------------- zoom */

  function applyZoom() {
    const stage = byId("bkStage");
    const wrap = byId("bkZoomWrap");
    if (!stage || !wrap) return;
    const z = bk.zoom;
    stage.style.transform = z === 1 ? "" : "scale(" + z + ")";
    wrap.style.width = z === 1 ? "" : stage.offsetWidth * z + "px";
    wrap.style.height = z === 1 ? "" : stage.offsetHeight * z + "px";
    byId("bkZoomVal").textContent = faDigits(Math.round(z * 100)) + "٪";
  }
  function setZoom(z) {
    bk.zoom = Math.max(ZOOM_STEPS[0], Math.min(1, z));
    applyZoom();
  }
  function zoomStep(dir) {
    const idx = ZOOM_STEPS.findIndex((s) => s >= bk.zoom - 0.001);
    const next = ZOOM_STEPS[Math.max(0, Math.min(ZOOM_STEPS.length - 1, idx + dir))];
    setZoom(next);
  }
  function zoomFit() {
    const scroll = byId("bkScroll");
    const stage = byId("bkStage");
    if (!scroll || !stage) return;
    const natural = stage.offsetWidth;
    setZoom(natural ? Math.min(1, (scroll.clientWidth - 8) / natural) : 1);
  }

  /* ------------------------------------------------------- focus keeping */

  function captureFocus() {
    const el = document.activeElement;
    if (!el || !el.closest || !el.closest("#bkStage")) return null;
    const sel = el.dataset.team !== undefined
      ? '[data-team="' + el.dataset.team + '"]'
      : el.dataset.key && el.classList.contains("bk-score-input")
      ? '.bk-score-input[data-key="' + el.dataset.key + '"][data-side="' + el.dataset.side + '"]'
      : null;
    return sel ? { sel, value: el.value, start: el.selectionStart } : null;
  }
  function restoreFocus(saved) {
    if (!saved) return;
    const el = document.querySelector("#bkStage " + saved.sel);
    if (!el) return;
    el.focus({ preventScroll: true });
    try {
      if (saved.start !== null && saved.start !== undefined) el.setSelectionRange(saved.start, saved.start);
    } catch (e) {
      /* number inputs have no selection range */
    }
  }

  /* ------------------------------------------------------------ loading */

  const apiURL = (division) => "/api/bracket/?division=" + encodeURIComponent(division);

  function paintRefresh() {
    const btn = byId("bkRefresh");
    if (!btn) return;
    btn.disabled = S().loading;
    btn.classList.toggle("busy", S().loading);
  }

  // A fetch is always for one named division: the user may switch tabs while
  // it is in the air, and the answer must land in the state it was asked for.
  async function load({ quiet = false, auto = false, division = bk.division } = {}) {
    const view = S(division);
    if (view.loading) return;
    if (auto && view.fetchedAt && Date.now() - view.fetchedAt < MIN_AUTO_REFETCH_MS) return;
    view.loading = true;
    paintRefresh();
    if (!view.loadedOnce && division === bk.division) render();
    try {
      view.data = await api(apiURL(division));
      view.fetchedAt = new Date();
      view.loadedOnce = true;
      view.error = null;
    } catch (e) {
      view.error = e.message;
      if (!quiet) toast(e.message, "err");
    } finally {
      view.loading = false;
      paintRefresh();
    }
    if (division === bk.division) render();
    else paintDivisionTabs();
  }

  function paintSaveStatus(saved) {
    const chip = byId("bkSaveStatus");
    if (!chip) return;
    clearTimeout(bk.savedTimer);
    if (bk.saving > 0) {
      chip.hidden = false;
      chip.className = "bk-save-status saving";
      chip.textContent = "در حال ذخیره…";
    } else if (saved) {
      chip.hidden = false;
      chip.className = "bk-save-status saved";
      chip.textContent = "ذخیره شد ✓";
      bk.savedTimer = setTimeout(() => {
        chip.hidden = true;
      }, 1800);
    } else {
      chip.hidden = true;
    }
  }

  // Every edit is one small PATCH; the response is the whole bracket and
  // simply replaces what we have, so the screen is always the server's truth.
  async function patch(body) {
    const division = bk.division;
    const view = S(division);
    bk.saving += 1;
    paintSaveStatus();
    let ok = false;
    try {
      view.data = await api(apiURL(division), { method: "PATCH", body });
      view.fetchedAt = new Date();
      ok = true;
      if (division === bk.division) render();
      else paintDivisionTabs();
    } catch (e) {
      toast(e.message, "err");
      // The server refused, so what is on screen may no longer be what is
      // stored. Resync rather than leave a rejected value looking saved.
      await load({ quiet: true, division });
    } finally {
      bk.saving -= 1;
      paintSaveStatus(ok);
    }
  }

  /* ------------------------------------------------------------- wiring */

  function readScore(k) {
    const inputs = document.querySelectorAll('#bkStage .bk-score-input[data-key="' + k + '"]');
    const values = [null, null];
    inputs.forEach((input) => {
      const v = input.value.trim();
      values[parseInt(input.dataset.side, 10)] = v === "" ? null : Math.max(0, Math.min(99, parseInt(v, 10) || 0));
    });
    if (values[0] === null && values[1] === null) return null;
    return [values[0] === null ? 0 : values[0], values[1] === null ? 0 : values[1]];
  }

  function wire() {
    byId("bkRefresh")?.addEventListener("click", () => load());
    document.querySelectorAll(".bk-div-tab").forEach((btn) => {
      btn.addEventListener("click", () => switchDivision(btn.dataset.division));
      btn.addEventListener("keydown", (e) => {
        // Arrow keys move between the two tabs, as a tablist should.
        if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
        e.preventDefault();
        const other = DIVISIONS.find((d) => d !== bk.division);
        switchDivision(other);
        document.querySelector('.bk-div-tab[data-division="' + other + '"]')?.focus();
      });
    });
    byId("bkZoomOut")?.addEventListener("click", () => zoomStep(-1));
    byId("bkZoomIn")?.addEventListener("click", () => zoomStep(1));
    byId("bkZoomFit")?.addEventListener("click", zoomFit);
    window.addEventListener("resize", () => {
      if (byId("bkGrid")) {
        drawLines();
        applyZoom();
      }
    });

    byId("bracketTab")?.addEventListener("click", () => {
      switchView("bracket");
      if (location.hash) history.replaceState(null, "", location.pathname + location.search);
      load({ quiet: true, auto: true });
      // The stage only has a real width once the view is visible.
      requestAnimationFrame(() => {
        drawLines();
        applyZoom();
      });
    });

    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible" && S().loadedOnce) load({ quiet: true, auto: true });
    });
    setInterval(() => {
      const el = byId("bkUpdated");
      if (el && S().fetchedAt) el.textContent = "به‌روزرسانی: " + relTime(S().fetchedAt.toISOString());
    }, 30000);

    // ---- admin bar
    byId("bkEditToggle")?.addEventListener("click", () => {
      S().editing = !S().editing;
      render();
    });
    byId("bkTitleInput")?.addEventListener("change", (e) => patch({ title: e.target.value }));
    byId("bkPublished")?.addEventListener("change", (e) => patch({ published: e.target.checked }));
    byId("bkSizeSelect")?.addEventListener("change", (e) => {
      const size = parseInt(e.target.value, 10);
      if (size === S().data.size) return;
      const hasResults = Object.keys(S().data.results || {}).length > 0;
      if (
        hasResults &&
        !confirm("با تغییر تعداد تیم‌ها، همهٔ نتایج پاک می‌شود (نام تیم‌ها می‌ماند). ادامه می‌دهی؟")
      ) {
        e.target.value = String(S().data.size);
        return;
      }
      patch({ size });
    });
    byId("bkResetResults")?.addEventListener("click", () => {
      if (confirm("همهٔ نتایج پاک شود؟ نام تیم‌ها دست‌نخورده می‌ماند.")) patch({ reset_results: true });
    });
    byId("bkAutofill")?.addEventListener("click", () => {
      const d = S().data;
      const used = new Set(d.teams.filter(Boolean));
      const pool = (d.suggestions || []).filter((u) => !used.has(u));
      for (let i = pool.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [pool[i], pool[j]] = [pool[j], pool[i]];
      }
      const teams = {};
      d.teams.forEach((name, idx) => {
        if (!name && pool.length) teams[idx] = pool.shift();
      });
      if (!Object.keys(teams).length) {
        toast("جای خالی‌ای برای پر کردن نیست، یا کاربر آزادی نمانده.", "err");
        return;
      }
      patch({ teams });
    });

    // ---- inline editing inside the grid (delegated; the grid is re-rendered often)
    const wrap = byId("bkStageWrap");
    wrap?.addEventListener("change", (e) => {
      const t = e.target;
      if (t.classList.contains("bk-name-input")) {
        patch({ teams: { [t.dataset.team]: t.value } });
      } else if (t.classList.contains("bk-score-input")) {
        const k = t.dataset.key;
        const score = readScore(k);
        let winner = decided(k);
        // A clear scoreline decides the match by itself; a draw (penalties)
        // still needs the tick.
        if (score && score[0] !== score[1]) winner = score[0] > score[1] ? 0 : 1;
        patch({ results: { [k]: { winner, score } } });
      }
    });
    wrap?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && e.target.matches(".bk-name-input,.bk-score-input")) {
        e.preventDefault();
        e.target.blur(); // fires change
      }
    });
    wrap?.addEventListener("click", (e) => {
      const win = e.target.closest(".bk-win");
      if (win) {
        const k = win.dataset.key;
        const side = parseInt(win.dataset.side, 10);
        const winner = decided(k) === side ? null : side;
        patch({ results: { [k]: { winner, score: scoreOf(k) } } });
        return;
      }
      const clear = e.target.closest(".bk-clear");
      if (clear) patch({ results: { [clear.dataset.clear]: { winner: null, score: null } } });
    });
  }

  function start() {
    if (!byId("bracketView")) return;
    wire();
    load({ quiet: true });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
