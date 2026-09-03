/* ===== In-app inbox: bell, panel, detail view, admin composer =====
 *
 * Loaded after game.js and reuses its globals ($, csrf, showToast, switchView,
 * toFa) — both are classic scripts sharing one global scope. Everything else
 * lives in this file so the game code stays untouched.
 *
 * There is NO realtime here. No SSE, no WebSocket, no background poll. The
 * inbox is exactly as fresh as the last fetch, which is why the refresh button
 * and the "not automatic" note in the panel are load-bearing UI, not decoration.
 */
(function () {
  "use strict";

  const byId = (id) => document.getElementById(id);
  const toast = (text, kind) =>
    typeof showToast === "function" ? showToast(text, kind) : console.log(text);
  const faDigits = (value) =>
    typeof toFa === "function" ? toFa(value) : String(value);

  const esc = (value) =>
    String(value == null ? "" : value).replace(
      /[&<>"']/g,
      (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );

  const IS_ADMIN = !!window.IS_MESSAGING_ADMIN;
  const TITLE_MAX = 120;
  // Floor between *automatic* refetches. Opening the panel and flipping back to
  // the tab are both cheap triggers on their own, but someone alt-tabbing sends
  // a burst of them. The Refresh button ignores this and always fetches --
  // pressing it is an explicit "check now".
  const MIN_AUTO_REFETCH_MS = 20000;

  /* ------------------------------------------------------------- fetch layer */

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
    if (!response.ok) {
      const err = new Error((data && data.error) || "خطای سرور (" + response.status + ").");
      err.status = response.status;
      throw err;
    }
    return data;
  }

  /* ------------------------------------------------------------ time helpers */

  const dateFmt = new Intl.DateTimeFormat("fa-IR", { dateStyle: "medium" });
  const fullFmt = new Intl.DateTimeFormat("fa-IR", {
    dateStyle: "full",
    timeStyle: "short",
  });

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

  function fullTime(iso) {
    if (!iso) return "";
    const date = new Date(iso);
    return isFinite(date.getTime()) ? fullFmt.format(date) : "";
  }

  /* ================================================================= INBOX == */

  const inbox = {
    items: [],
    unread: 0,
    total: 0,
    fetchedAt: null,
    loading: false,
    loadedOnce: false,
    // Kept apart from "no messages": telling someone their inbox is empty when
    // the request actually failed is a lie they would act on.
    error: null,
    open: false,
  };

  function paintBadge() {
    const bell = byId("inboxBell");
    const badge = byId("inboxBadge");
    if (!bell || !badge) return;
    const count = inbox.unread;
    bell.classList.toggle("has-unread", count > 0);
    badge.hidden = count === 0;
    badge.textContent = count > 99 ? "+۹۹" : faDigits(count);
    // The count goes in the label too, and the visual badge is aria-hidden, so
    // a screen reader hears it once rather than twice.
    bell.setAttribute(
      "aria-label",
      count > 0 ? "پیام‌ها — " + faDigits(count) + " خوانده‌نشده" : "پیام‌ها"
    );
    const pill = byId("ibxUnreadPill");
    if (pill) {
      pill.hidden = count === 0;
      pill.textContent = faDigits(count) + " تازه";
    }
  }

  function paintUpdatedAt() {
    const text = inbox.fetchedAt
      ? "به‌روزرسانی: " + relTime(inbox.fetchedAt.toISOString())
      : "هنوز به‌روزرسانی نشده";
    ["inboxUpdated", "inboxPageUpdated"].forEach((id) => {
      const el = byId(id);
      if (el) el.textContent = text;
    });
  }

  function cardHTML(item) {
    const state = item.is_read ? "is-read" : "is-unread";
    const dot = item.is_read ? "" : '<span class="ibx-dot" aria-hidden="true"></span>';
    const excerpt = item.excerpt || "(بدون متن)";
    return (
      '<button type="button" class="ibx-card ' +
      state +
      '" data-note="' +
      item.id +
      '">' +
      '<span class="ibx-meta">' +
      dot +
      '<span class="ibx-sender">' +
      esc(item.sender) +
      "</span>" +
      '<span class="ibx-time">' +
      esc(relTime(item.sent_at)) +
      "</span>" +
      "</span>" +
      '<span class="ibx-title">' +
      esc(item.title) +
      "</span>" +
      '<span class="ibx-excerpt">' +
      esc(excerpt) +
      "</span>" +
      (item.is_read ? "" : '<span class="sr-only">خوانده‌نشده</span>') +
      "</button>"
    );
  }

  function emptyHTML() {
    return (
      '<div class="ibx-empty"><span class="ibx-empty-ico" aria-hidden="true">📭</span>' +
      "هنوز پیامی نداری.<br>پیام‌های مدیران اینجا نمایش داده می‌شوند.</div>"
    );
  }

  function errorHTML() {
    return (
      '<div class="ibx-empty"><span class="ibx-empty-ico" aria-hidden="true">⚠️</span>' +
      "پیام‌ها بارگذاری نشد.<br>دکمهٔ «تازه‌سازی» را بزن.</div>"
    );
  }

  function skeletonHTML() {
    return '<div class="ibx-skel"></div><div class="ibx-skel"></div><div class="ibx-skel"></div>';
  }

  function paintLists() {
    let html;
    if (inbox.loading && !inbox.loadedOnce) html = skeletonHTML();
    else if (inbox.items.length) html = inbox.items.map(cardHTML).join("");
    else if (inbox.error) html = errorHTML();
    else html = emptyHTML();
    ["inboxList", "inboxPageList"].forEach((id) => {
      const el = byId(id);
      if (el) el.innerHTML = html;
    });
    const readAllDisabled = inbox.unread === 0;
    ["inboxReadAll", "inboxPageReadAll"].forEach((id) => {
      const el = byId(id);
      if (el) el.disabled = readAllDisabled;
    });
  }

  function setRefreshBusy(busy) {
    ["inboxRefresh", "inboxPageRefresh"].forEach((id) => {
      const button = byId(id);
      if (!button) return;
      button.disabled = busy;
      button.classList.toggle("busy", busy);
    });
  }

  async function loadInbox({ quiet = false, auto = false } = {}) {
    if (inbox.loading) return;
    if (auto && inbox.fetchedAt && Date.now() - inbox.fetchedAt < MIN_AUTO_REFETCH_MS) {
      return;
    }
    inbox.loading = true;
    setRefreshBusy(true);
    if (!inbox.loadedOnce) paintLists();
    try {
      const data = await api("/api/notifications/");
      inbox.items = data.results || [];
      inbox.unread = data.unread || 0;
      inbox.total = data.total || 0;
      inbox.fetchedAt = new Date();
      inbox.loadedOnce = true;
      inbox.error = null;
    } catch (e) {
      inbox.error = e.message;
      if (!quiet) toast(e.message, "err");
    } finally {
      inbox.loading = false;
      setRefreshBusy(false);
    }
    paintBadge();
    paintLists();
    paintUpdatedAt();
  }

  async function markRead(ids) {
    const pending = ids.filter((id) => {
      const item = inbox.items.find((row) => row.id === id);
      // An id we hold locally and know to be read is worth skipping. One we
      // have never seen -- opened straight from a link, or older than the
      // listing cap -- goes to the server, which ignores it if it is already
      // read. Filtering those out here is how a bookmarked message stays
      // unread for ever.
      return !item || !item.is_read;
    });
    if (!pending.length) return;
    try {
      const data = await api("/api/notifications/read/", {
        method: "POST",
        body: { ids: pending },
      });
      pending.forEach((id) => {
        const item = inbox.items.find((row) => row.id === id);
        if (item) {
          item.is_read = true;
          item.read_at = new Date().toISOString();
        }
      });
      inbox.unread = data.unread;
      paintBadge();
      paintLists();
    } catch (e) {
      toast(e.message, "err");
    }
  }

  async function markAllRead() {
    try {
      const data = await api("/api/notifications/read-all/", { method: "POST" });
      inbox.items.forEach((item) => {
        item.is_read = true;
      });
      inbox.unread = data.unread;
      paintBadge();
      paintLists();
      if (data.marked) toast("همهٔ پیام‌ها خوانده‌شده علامت خوردند.", "ok");
    } catch (e) {
      toast(e.message, "err");
    }
  }

  /* ------------------------------------------------------------- the drawer */

  let lastFocused = null;

  function openDrawer() {
    const drawer = byId("inboxDrawer");
    const backdrop = byId("inboxBackdrop");
    if (!drawer || !backdrop) return;
    lastFocused = document.activeElement;
    drawer.hidden = false;
    backdrop.hidden = false;
    inbox.open = true;
    byId("inboxBell")?.setAttribute("aria-expanded", "true");
    document.body.style.overflow = "hidden";
    byId("inboxClose")?.focus();
    paintUpdatedAt();
    loadInbox({ quiet: true, auto: true }); // opening the panel is a moment to resync
  }

  function closeDrawer() {
    const drawer = byId("inboxDrawer");
    const backdrop = byId("inboxBackdrop");
    if (!drawer || !backdrop) return;
    drawer.hidden = true;
    backdrop.hidden = true;
    inbox.open = false;
    byId("inboxBell")?.setAttribute("aria-expanded", "false");
    document.body.style.overflow = "";
    if (lastFocused && lastFocused.focus) lastFocused.focus();
  }

  /* -------------------------------------------------------- the detail view */

  function showInboxList() {
    byId("inboxListPane").hidden = false;
    byId("inboxDetailPane").hidden = true;
  }

  async function showInboxDetail(id) {
    const listPane = byId("inboxListPane");
    const pane = byId("inboxDetailPane");
    if (!pane) return;
    listPane.hidden = true;
    pane.hidden = false;

    let item = inbox.items.find((row) => row.id === id);
    if (!item) {
      try {
        const data = await api("/api/notifications/" + id + "/");
        item = data.notification;
        inbox.unread = data.unread;
        paintBadge();
      } catch (e) {
        toast(e.message, "err");
        location.hash = "#/inbox";
        return;
      }
    }

    const sender = item.sender || "مدیر";
    byId("ibxDetailAvatar").textContent = sender.trim().charAt(0) || "؟";
    byId("ibxDetailSender").textContent = sender;
    byId("ibxDetailTime").textContent = fullTime(item.sent_at);
    byId("ibxDetailTitle").textContent = item.title;
    const body = byId("ibxDetailBody");
    body.textContent = item.body || "(این پیام متنی ندارد.)";
    body.classList.toggle("is-empty", !item.body);
    window.scrollTo({ top: 0, behavior: "smooth" });

    // Render first, then mark read — the GET that fetched it deliberately did
    // not touch read_at, so this is the only thing that moves the badge.
    markRead([id]);
  }

  /* ------------------------------------------------------------ hash routing */

  function route() {
    const hash = location.hash || "";
    const match = /^#\/inbox(?:\/(\d+))?$/.exec(hash);
    if (!match) {
      if (document.getElementById("inboxView")?.classList.contains("active")) {
        switchView("builder");
      }
      return;
    }
    closeDrawer();
    switchView("inbox");
    if (!inbox.loadedOnce) loadInbox({ quiet: true });
    if (match[1]) showInboxDetail(parseInt(match[1], 10));
    else showInboxList();
  }

  /* ============================================================== COMPOSER == */

  const composer = {
    tab: "compose",
    editingId: null,
    toEveryone: false,
    // The source of truth for the picker. The checkboxes are rendered *from*
    // this on every paint and never read back — let the DOM own the state and
    // the reach count quietly stops matching what actually gets sent.
    selected: new Set(),
    // Last reach the server reported. Kept so a later keystroke in the title
    // field re-evaluates Send against the real number rather than guessing.
    reach: 0,
    users: [],
    usersLoaded: false,
    search: "",
    drafts: [],
    sent: [],
    receiptFilter: "unread",
    receipts: null,
  };

  function audienceLabel(row) {
    if (row.to_everyone) return "همهٔ کاربران";
    if (row.audience_count) return faDigits(row.audience_count) + " کاربر انتخاب‌شده";
    return "بدون گیرنده";
  }

  let previewTimer = null;
  let previewToken = 0;

  function schedulePreview() {
    composer.reach = 0;
    syncSendEnabled();
    const readout = byId("audReach");
    if (readout) {
      readout.className = "aud-reach is-loading";
      readout.textContent = "…";
    }
    clearTimeout(previewTimer);
    previewTimer = setTimeout(runPreview, 300);
  }

  async function runPreview() {
    const readout = byId("audReach");
    if (!readout) return;
    const token = ++previewToken;
    try {
      const data = await api("/api/messages/audience-preview/", {
        method: "POST",
        body: {
          to_everyone: composer.toEveryone,
          users: Array.from(composer.selected),
        },
      });
      if (token !== previewToken) return; // a newer keystroke already won
      readout.className = "aud-reach" + (data.count ? "" : " is-zero");
      readout.textContent = data.to_everyone
        ? "همه — " + faDigits(data.count) + " نفر"
        : data.count
        ? "می‌رسد به " + faDigits(data.count) + " نفر"
        : "هیچ‌کس انتخاب نشده";
      composer.reach = data.count;
      syncSendEnabled();
    } catch (e) {
      if (token !== previewToken) return;
      readout.className = "aud-reach is-zero";
      readout.textContent = "شمارش نشد";
      composer.reach = 0;
      syncSendEnabled();
    }
  }

  function syncSendEnabled() {
    const title = (byId("msgTitle")?.value || "").trim();
    const send = byId("msgSend");
    if (send) send.disabled = !title || !composer.reach;
  }

  function paintAudience() {
    const everyone = byId("audEveryone");
    const picker = byId("audPicker");
    if (!everyone || !picker) return;
    everyone.checked = composer.toEveryone;
    // "Everyone" makes the rest irrelevant, so it collapses rather than sitting
    // there inviting a selection that would be ignored.
    picker.hidden = composer.toEveryone;

    const query = composer.search.trim().toLowerCase();
    const shown = composer.users.filter(
      (user) =>
        !query ||
        user.username.toLowerCase().includes(query) ||
        (user.label || "").toLowerCase().includes(query)
    );
    const list = byId("audList");
    if (!list) return;
    if (!composer.usersLoaded) {
      list.innerHTML = '<div class="aud-none">در حال بارگذاری کاربران…</div>';
      return;
    }
    if (!shown.length) {
      list.innerHTML = '<div class="aud-none">کاربری با این نام پیدا نشد.</div>';
      return;
    }
    list.innerHTML = shown
      .map((user) => {
        const checked = composer.selected.has(user.id) ? " checked" : "";
        const sub =
          user.label && user.label !== user.username
            ? '<span class="aud-sub">' + esc(user.label) + "</span>"
            : "";
        const tag = user.is_admin ? '<span class="aud-tag">مدیر</span>' : "";
        return (
          '<label class="aud-row"><input type="checkbox" data-user="' +
          user.id +
          '"' +
          checked +
          '><span class="aud-name">' +
          esc(user.username) +
          "</span>" +
          sub +
          tag +
          "</label>"
        );
      })
      .join("");

    const badge = byId("audSelectedCount");
    if (badge) {
      badge.textContent = composer.selected.size
        ? faDigits(composer.selected.size) + " انتخاب‌شده"
        : "";
    }
  }

  async function loadAudience() {
    if (composer.usersLoaded) {
      schedulePreview();
      return;
    }
    try {
      const data = await api("/api/messages/audience/");
      composer.users = data.users || [];
      composer.usersLoaded = true;
      paintAudience();
      // First reach readout. Without it the chip sits on its placeholder and
      // the admin has no idea whether "nobody selected" is real or just unloaded.
      schedulePreview();
    } catch (e) {
      toast(e.message, "err");
    }
  }

  function resetComposer() {
    composer.editingId = null;
    composer.toEveryone = false;
    composer.selected = new Set();
    composer.search = "";
    byId("msgTitle").value = "";
    byId("msgBody").value = "";
    byId("audSearch").value = "";
    paintEditingBadge();
    paintTitleCounter();
    paintAudience();
    schedulePreview();
  }

  function paintEditingBadge() {
    const badge = byId("msgEditingBadge");
    if (!badge) return;
    badge.hidden = !composer.editingId;
    badge.textContent = composer.editingId
      ? "در حال ویرایش پیش‌نویس #" + faDigits(composer.editingId)
      : "";
  }

  function paintTitleCounter() {
    const input = byId("msgTitle");
    const counter = byId("msgTitleCount");
    if (!input || !counter) return;
    const used = input.value.length;
    counter.textContent = faDigits(used) + "/" + faDigits(TITLE_MAX);
    counter.classList.toggle("near", used > TITLE_MAX - 20);
  }

  function composerPayload(extra) {
    return Object.assign(
      {
        title: (byId("msgTitle").value || "").trim(),
        body: byId("msgBody").value || "",
        to_everyone: composer.toEveryone,
        users: Array.from(composer.selected),
      },
      extra || {}
    );
  }

  async function saveComposer({ send }) {
    const payload = composerPayload(send ? { send: true } : null);
    if (!payload.title) {
      toast("عنوان پیام را بنویس.", "err");
      return;
    }
    const buttons = [byId("msgSend"), byId("msgSaveDraft")].filter(Boolean);
    buttons.forEach((b) => (b.disabled = true));
    try {
      let data;
      if (composer.editingId) {
        await api("/api/messages/" + composer.editingId + "/", {
          method: "PATCH",
          body: payload,
        });
        data = send
          ? await api("/api/messages/" + composer.editingId + "/send/", { method: "POST" })
          : { message: "پیش‌نویس به‌روزرسانی شد." };
      } else {
        data = await api("/api/messages/", { method: "POST", body: payload });
      }
      toast(data.message || "انجام شد.", "ok");
      resetComposer();
      // switchComposerTab loads whichever list it opens, so only the tab we are
      // *not* moving to needs refreshing by hand.
      if (send) switchComposerTab("sent");
      else await loadMessages("draft");
    } catch (e) {
      toast(e.message, "err");
    } finally {
      buttons.forEach((b) => (b.disabled = false));
      syncSendEnabled();
      schedulePreview();
    }
  }

  /* -------------------------------------------------------- drafts and sent */

  function draftRowHTML(row) {
    return (
      '<div class="msg-row"><div class="msg-row-main">' +
      '<div class="msg-row-title">' +
      esc(row.title) +
      "</div>" +
      '<p class="msg-row-excerpt">' +
      esc(row.excerpt || "(بدون متن)") +
      "</p>" +
      '<div class="msg-row-meta"><span class="msg-chip' +
      (row.to_everyone ? " everyone" : "") +
      '">' +
      esc(audienceLabel(row)) +
      "</span><span>ویرایش: " +
      esc(relTime(row.updated_at)) +
      "</span></div></div>" +
      '<div class="msg-row-actions">' +
      '<button class="mini" data-draft-edit="' +
      row.id +
      '">✏️ ویرایش</button>' +
      '<button class="mini primary" data-draft-send="' +
      row.id +
      '">📨 ارسال</button>' +
      '<button class="mini danger" data-draft-delete="' +
      row.id +
      '">🗑 حذف</button>' +
      "</div></div>"
    );
  }

  function sentRowHTML(row) {
    const delivered = row.delivered || 0;
    const read = row.read || 0;
    return (
      '<div class="msg-row"><div class="msg-row-main">' +
      '<div class="msg-row-title">' +
      esc(row.title) +
      "</div>" +
      '<p class="msg-row-excerpt">' +
      esc(row.excerpt || "(بدون متن)") +
      "</p>" +
      '<div class="msg-row-meta"><span class="msg-chip' +
      (row.to_everyone ? " everyone" : "") +
      '">' +
      esc(audienceLabel(row)) +
      "</span><span>" +
      esc(relTime(row.sent_at)) +
      "</span><span>از: " +
      esc(row.sender) +
      "</span></div></div>" +
      '<div class="msg-row-actions">' +
      '<button class="read-figure" data-receipts="' +
      row.id +
      '" title="چه کسانی خوانده‌اند؟">' +
      faDigits(read) +
      "/" +
      faDigits(delivered) +
      " خوانده ←</button>" +
      "</div></div>"
    );
  }

  async function loadMessages(status) {
    const container = byId(status === "draft" ? "draftsList" : "sentList");
    if (!container) return;
    try {
      const data = await api("/api/messages/?status=" + status);
      const rows = data.results || [];
      if (status === "draft") {
        composer.drafts = rows;
        const count = byId("draftsCount");
        if (count) {
          count.textContent = rows.length ? faDigits(rows.length) : "";
          count.hidden = !rows.length;
        }
        container.innerHTML = rows.length
          ? rows.map(draftRowHTML).join("")
          : '<div class="ibx-empty"><span class="ibx-empty-ico" aria-hidden="true">📝</span>پیش‌نویسی نداری.</div>';
      } else {
        composer.sent = rows;
        container.innerHTML = rows.length
          ? rows.map(sentRowHTML).join("")
          : '<div class="ibx-empty"><span class="ibx-empty-ico" aria-hidden="true">📤</span>هنوز پیامی ارسال نشده است.</div>';
      }
    } catch (e) {
      toast(e.message, "err");
    }
  }

  function editDraft(id) {
    const row = composer.drafts.find((draft) => draft.id === id);
    if (!row) return;
    composer.editingId = id;
    composer.toEveryone = !!row.to_everyone;
    composer.selected = new Set(row.users || []);
    byId("msgTitle").value = row.title;
    byId("msgBody").value = row.body || "";
    paintEditingBadge();
    paintTitleCounter();
    paintAudience();
    schedulePreview();
    switchComposerTab("compose");
    byId("msgTitle").focus();
  }

  async function sendDraft(id) {
    if (!confirm("این پیش‌نویس ارسال شود؟ پس از ارسال، دیگر قابل ویرایش نیست.")) return;
    try {
      const data = await api("/api/messages/" + id + "/send/", { method: "POST" });
      toast(data.message, "ok");
      if (composer.editingId === id) resetComposer();
      await Promise.all([loadMessages("draft"), loadMessages("sent")]);
      switchComposerTab("sent");
    } catch (e) {
      toast(e.message, "err");
    }
  }

  async function deleteDraft(id) {
    if (!confirm("این پیش‌نویس حذف شود؟")) return;
    try {
      const data = await api("/api/messages/" + id + "/", { method: "DELETE" });
      toast(data.message, "ok");
      if (composer.editingId === id) resetComposer();
      loadMessages("draft");
    } catch (e) {
      toast(e.message, "err");
    }
  }

  /* ---------------------------------------------------------- read receipts */

  function paintReceipts() {
    const data = composer.receipts;
    if (!data) return;
    byId("rcptTitle").textContent = data.message.title;
    const body = byId("rcptBody");
    body.textContent = data.message.body || "(بدون متن)";
    const percent = data.delivered ? Math.round((data.read / data.delivered) * 100) : 0;
    byId("rcptBar").style.width = percent + "%";
    byId("rcptStat").textContent =
      faDigits(data.read) +
      " نفر از " +
      faDigits(data.delivered) +
      " نفر خوانده‌اند (" +
      faDigits(percent) +
      "٪)";

    const rows =
      composer.receiptFilter === "unread"
        ? data.recipients.filter((row) => !row.is_read)
        : data.recipients;
    const list = byId("rcptList");
    list.innerHTML = rows.length
      ? rows
          .map(
            (row) =>
              '<div class="rcpt-row"><span class="rcpt-state ' +
              (row.is_read ? "read" : "unread") +
              '">' +
              (row.is_read ? "خوانده" : "خوانده‌نشده") +
              '</span><span class="rcpt-who">' +
              esc(row.username) +
              (row.label && row.label !== row.username ? " — " + esc(row.label) : "") +
              '</span><span class="rcpt-when">' +
              esc(row.is_read ? relTime(row.read_at) : "—") +
              "</span></div>"
          )
          .join("")
      : '<div class="ibx-empty"><span class="ibx-empty-ico" aria-hidden="true">🎉</span>همه این پیام را خوانده‌اند.</div>';

    document.querySelectorAll("[data-rfilter]").forEach((button) => {
      button.classList.toggle(
        "active",
        button.dataset.rfilter === composer.receiptFilter
      );
    });
  }

  async function openReceipts(id) {
    try {
      composer.receipts = await api("/api/messages/" + id + "/recipients/");
      // Unread first is the default because that is the list an admin actually
      // wants — the people to chase.
      composer.receiptFilter = "unread";
      switchComposerTab("receipts");
      paintReceipts();
    } catch (e) {
      toast(e.message, "err");
    }
  }

  /* ----------------------------------------------------------- composer tabs */

  function switchComposerTab(tab) {
    composer.tab = tab;
    document.querySelectorAll(".mtab-pane").forEach((pane) => {
      pane.classList.toggle("active", pane.id === "mtab-" + tab);
    });
    // Receipts are a drill-down from Sent, not a fourth tab, so Sent stays lit
    // while they are open. Letting every tab go dark reads as a broken page.
    const litTab = tab === "receipts" ? "sent" : tab;
    document.querySelectorAll("[data-mtab]").forEach((button) => {
      button.classList.toggle("active", button.dataset.mtab === litTab);
    });
    if (tab === "compose") loadAudience();
    if (tab === "drafts") loadMessages("draft");
    if (tab === "sent") loadMessages("sent");
  }

  /* ------------------------------------------------------------------- wiring */

  function wireInbox() {
    byId("inboxBell")?.addEventListener("click", () =>
      inbox.open ? closeDrawer() : openDrawer()
    );
    byId("inboxClose")?.addEventListener("click", closeDrawer);
    byId("inboxBackdrop")?.addEventListener("click", closeDrawer);
    byId("inboxSeeAll")?.addEventListener("click", () => {
      location.hash = "#/inbox";
    });
    byId("inboxBack")?.addEventListener("click", () => {
      location.hash = "#/inbox";
    });
    ["inboxRefresh", "inboxPageRefresh"].forEach((id) =>
      byId(id)?.addEventListener("click", () => loadInbox())
    );
    ["inboxReadAll", "inboxPageReadAll"].forEach((id) =>
      byId(id)?.addEventListener("click", markAllRead)
    );

    document.addEventListener("click", (event) => {
      const card = event.target.closest?.(".ibx-card");
      if (card && card.dataset.note) {
        // A separate view, never an inline expand: a long message destroys a
        // list that looked fine with two-line ones.
        location.hash = "#/inbox/" + card.dataset.note;
      }
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && inbox.open) closeDrawer();
    });

    // Cheap, non-annoying resync: coming back to the tab is a moment the user
    // already expects to see something new.
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible" && inbox.loadedOnce) {
        loadInbox({ quiet: true, auto: true });
      }
    });

    // Keeps "updated 4 minutes ago" honest without touching the network.
    setInterval(paintUpdatedAt, 30000);

    window.addEventListener("hashchange", route);
    document.querySelectorAll(".nav button").forEach((button) =>
      button.addEventListener("click", () => {
        if (location.hash) {
          history.replaceState(null, "", location.pathname + location.search);
        }
      })
    );
  }

  function wireComposer() {
    document
      .querySelectorAll("[data-mtab]")
      .forEach((button) =>
        button.addEventListener("click", () => switchComposerTab(button.dataset.mtab))
      );

    byId("audEveryone")?.addEventListener("change", (event) => {
      composer.toEveryone = event.target.checked;
      paintAudience();
      schedulePreview();
    });
    byId("audSearch")?.addEventListener("input", (event) => {
      composer.search = event.target.value;
      paintAudience();
    });
    byId("audList")?.addEventListener("change", (event) => {
      const id = parseInt(event.target.dataset.user || "", 10);
      if (!id) return;
      if (event.target.checked) composer.selected.add(id);
      else composer.selected.delete(id);
      paintAudience(); // re-render from state; the DOM is output only
      schedulePreview();
    });
    byId("audSelectShown")?.addEventListener("click", () => {
      const query = composer.search.trim().toLowerCase();
      composer.users
        .filter(
          (user) =>
            !query ||
            user.username.toLowerCase().includes(query) ||
            (user.label || "").toLowerCase().includes(query)
        )
        .forEach((user) => composer.selected.add(user.id));
      paintAudience();
      schedulePreview();
    });
    byId("audClear")?.addEventListener("click", () => {
      composer.selected.clear();
      paintAudience();
      schedulePreview();
    });

    byId("msgTitle")?.addEventListener("input", () => {
      paintTitleCounter();
      syncSendEnabled();
    });
    byId("msgSend")?.addEventListener("click", () => saveComposer({ send: true }));
    byId("msgSaveDraft")?.addEventListener("click", () => saveComposer({ send: false }));
    byId("msgResetForm")?.addEventListener("click", resetComposer);

    byId("draftsList")?.addEventListener("click", (event) => {
      const target = event.target.closest("[data-draft-edit],[data-draft-send],[data-draft-delete]");
      if (!target) return;
      if (target.dataset.draftEdit) editDraft(parseInt(target.dataset.draftEdit, 10));
      else if (target.dataset.draftSend) sendDraft(parseInt(target.dataset.draftSend, 10));
      else if (target.dataset.draftDelete) deleteDraft(parseInt(target.dataset.draftDelete, 10));
    });
    byId("sentList")?.addEventListener("click", (event) => {
      const target = event.target.closest("[data-receipts]");
      if (target) openReceipts(parseInt(target.dataset.receipts, 10));
    });
    byId("rcptBack")?.addEventListener("click", () => switchComposerTab("sent"));
    document.querySelectorAll("[data-rfilter]").forEach((button) =>
      button.addEventListener("click", () => {
        composer.receiptFilter = button.dataset.rfilter;
        paintReceipts();
      })
    );

    // game.js wires its nav buttons one by one, so this one is ours to switch.
    byId("messagesTab")?.addEventListener("click", () => {
      switchView("messages");
      switchComposerTab(composer.tab);
      loadMessages("draft"); // keeps the drafts tab count honest
    });
  }

  function start() {
    if (!byId("inboxBell")) return;
    wireInbox();
    if (IS_ADMIN) wireComposer();
    paintBadge();
    paintUpdatedAt();
    loadInbox({ quiet: true });
    route();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
