/* Paradise Island Launcher - frontend logic */
(function () {
  "use strict";

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  var state = {
    config: {}, meta: {}, accounts: [], active: "", instances: [], versions: [], java: [],
    lang: "zh-CN", page: "home", selected: "", installVersion: "",
    filter: "all", search: "", sort: "name",
    backgrounds: [], currentBg: 0, modal: null,
    progressTimer: null, progressKind: null,
    logTimer: null, logSource: "launcher", logVid: "", logAutoScroll: true
  };

  /* ---------------- helpers ---------------- */

  function t(key, vars) {
    var dict = (window.I18N && window.I18N[state.lang]) || {};
    var fallback = (window.I18N && window.I18N["en"]) || {};
    var text = dict[key] || fallback[key] || key;
    if (vars) {
      Object.keys(vars).forEach(function (k) {
        text = String(text).split("{" + k + "}").join(vars[k]);
      });
    }
    return text;
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function api(path, opts) {
    return fetch(path, opts).then(function (res) {
      var type = res.headers.get("content-type") || "";
      if (type.indexOf("application/json") === -1) throw new Error("HTTP " + res.status);
      return res.json();
    });
  }

  function post(path, data) {
    return api(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data || {})
    });
  }

  function formatBytes(bytes) {
    if (!bytes) return "0 B";
    var units = ["B", "KB", "MB", "GB"];
    var i = 0, n = Number(bytes);
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    return (i === 0 ? n : n.toFixed(1)) + " " + units[i];
  }

  function formatTime(ts) {
    if (!ts) return t("instances.neverPlayed");
    try {
      return new Date(ts * 1000).toLocaleString(state.lang, {
        year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit"
      });
    } catch (e) {
      return new Date(ts * 1000).toLocaleString();
    }
  }

  function avatarUrl(name) {
    return "https://mc-heads.net/avatar/" + encodeURIComponent(name || "Steve") + "/64";
  }

  function bodyUrl(name) {
    return "https://mc-heads.net/body/" + encodeURIComponent(name || "Steve") + "/200";
  }

  function attachImageFallback(img, fallback) {
    img.onerror = function () { img.onerror = null; img.src = fallback; };
  }

  function typeLabel(type) {
    if (type === "release") return t("filter.release");
    if (type === "snapshot") return t("filter.snapshot");
    return t("filter.old");
  }

  function loaderLabel(loader) {
    var key = "loader." + (loader || "vanilla");
    var label = t(key);
    return label === key ? (loader || "vanilla") : label;
  }

  function activeAccount() {
    for (var i = 0; i < state.accounts.length; i++) {
      if (state.accounts[i].uuid === state.active) return state.accounts[i];
    }
    return null;
  }

  function currentInstance() {
    for (var i = 0; i < state.instances.length; i++) {
      if (state.instances[i].id === state.selected && state.instances[i].installed) return state.instances[i];
    }
    return null;
  }

  function findInstance(id) {
    for (var i = 0; i < state.instances.length; i++) if (state.instances[i].id === id) return state.instances[i];
    return null;
  }

  /* ---------------- toast / modal ---------------- */

  function toast(message, type) {
    var wrap = $("#toastWrap");
    if (!wrap) return;
    var el = document.createElement("div");
    el.className = "toast " + (type || "");
    var dot = document.createElement("span"); dot.className = "dot";
    var text = document.createElement("span"); text.textContent = String(message == null ? "" : message);
    el.appendChild(dot);
    el.appendChild(text);
    wrap.appendChild(el);
    setTimeout(function () {
      el.classList.add("hide");
      setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 220);
    }, 3400);
  }

  function makeButton(label, cls, onClick) {
    var b = document.createElement("button");
    b.className = "btn " + (cls || "");
    b.textContent = label;
    if (onClick) b.addEventListener("click", onClick);
    return b;
  }

  var modalStack = [];

  function renderModal(opts) {
    $("#modalTitle").textContent = opts.title || "";
    var body = $("#modalBody");
    body.innerHTML = "";
    if (typeof opts.body === "string") body.innerHTML = opts.body;
    else if (opts.body) body.appendChild(opts.body);
    var foot = $("#modalFoot");
    foot.innerHTML = "";
    var buttons = opts.footer || [];
    buttons.forEach(function (b) { foot.appendChild(b); });
    foot.classList.toggle("hidden", buttons.length === 0);
    $("#modal").classList.toggle("wide", !!opts.wide);
    $("#modalBg").classList.add("show");
  }

  function openModal(opts) {
    if (state.modal) modalStack.push(state.modal);
    state.modal = opts || {};
    renderModal(state.modal);
  }

  function closeModal() {
    var opts = state.modal;
    state.modal = null;
    $("#modalBg").classList.remove("show");
    stopLogAuto();
    if (opts && opts.onClose) opts.onClose();
    if (modalStack.length) {
      state.modal = modalStack.pop();
      renderModal(state.modal);
    }
  }

  function confirmBox(message, danger) {
    return new Promise(function (resolve) {
      var done = false;
      var body = document.createElement("div");
      body.className = "muted";
      body.style.lineHeight = "1.7";
      body.textContent = message;
      function finish(value) {
        if (done) return;
        done = true;
        closeModal();
        resolve(value);
      }
      var cancel = makeButton(t("common.cancel"), "ghost", function () { finish(false); });
      var ok = makeButton(t("common.ok"), danger === false ? "primary" : "danger", function () { finish(true); });
      openModal({
        title: t("common.confirm"),
        body: body,
        footer: [cancel, ok],
        onClose: function () { if (!done) { done = true; resolve(false); } }
      });
    });
  }

  function showError(title, message) {
    var body = document.createElement("div");
    body.className = "log-box";
    body.style.height = "auto";
    body.style.maxHeight = "46vh";
    body.textContent = String(message || "");
    openModal({
      title: title,
      body: body,
      footer: [makeButton(t("common.close"), "primary", closeModal)]
    });
  }

  /* ---------------- theme / language ---------------- */

  function prefersDark() {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  function applyTheme(theme, persist) {
    state.config.theme = theme || "dark";
    var dark = theme !== "light" && !(theme === "system" && !prefersDark());
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    var use = $("#themeBtn use");
    if (use) use.setAttribute("href", dark ? "#i-sun" : "#i-moon");
    var sel = $("#themeSelect");
    if (sel) sel.value = state.config.theme;
    if (persist) post("/api/config", { theme: state.config.theme });
  }

  function applyLanguage(lang) {
    state.lang = (window.I18N && window.I18N[lang]) ? lang : "en";
    state.config.language = state.lang;
    document.documentElement.lang = state.lang;
    $$("[data-i18n]").forEach(function (el) { el.textContent = t(el.getAttribute("data-i18n")); });
    $$("[data-i18n-ph]").forEach(function (el) { el.placeholder = t(el.getAttribute("data-i18n-ph")); });
    buildDynamicSelects();
    renderAll();
  }

  /* ---------------- selects ---------------- */

  function fillSelect(select, items, value) {
    if (!select) return;
    select.innerHTML = "";
    items.forEach(function (item) {
      var opt = document.createElement("option");
      opt.value = item.value;
      opt.textContent = item.label;
      select.appendChild(opt);
    });
    if (value != null) select.value = value;
  }

  function buildDynamicSelects() {
    var loaderEl = $("#loaderSelect");
    fillSelect(loaderEl, [
      { value: "vanilla", label: loaderLabel("vanilla") },
      { value: "forge", label: "Forge" },
      { value: "neoforge", label: "NeoForge" },
      { value: "fabric", label: "Fabric" },
      { value: "quilt", label: "Quilt" }
    ], (loaderEl && loaderEl.value) || "vanilla");

    fillSelect($("#themeSelect"), [
      { value: "dark", label: t("theme.dark") },
      { value: "light", label: t("theme.light") },
      { value: "system", label: t("theme.system") }
    ], state.config.theme || "dark");

    var langs = (window.LANGUAGES || []).map(function (l) { return { value: l.code, label: l.name }; });
    fillSelect($("#languageSelect"), langs, state.lang);

    fillSelect($("#sourceSelect"), [
      { value: "bmclapi", label: "BMCLAPI" },
      { value: "official", label: "Official" }
    ], state.config.download_source || "bmclapi");

    fillSelect($("#instanceSort"), [
      { value: "name", label: t("instances.sortName") },
      { value: "recent", label: t("instances.sortRecent") }
    ], state.sort);
  }

  /* ---------------- rendering: home ---------------- */

  function currentBackgroundUrl() {
    var id = Number(state.config.current_background || 0);
    for (var i = 0; i < state.backgrounds.length; i++) {
      if (state.backgrounds[i].id === id) return state.backgrounds[i].url;
    }
    return state.backgrounds.length ? state.backgrounds[0].url : "/static/images/background_0.png";
  }

  function renderHome() {
    var bg = $("#homeBg");
    if (bg) bg.style.backgroundImage = 'url("' + currentBackgroundUrl() + '")';

    var acc = activeAccount();
    var name = acc ? acc.name : (state.config.last_username || "Steve");
    var avatar = $("#homeAvatar");
    if (avatar) { attachImageFallback(avatar, "/static/images/avatar.png"); avatar.src = avatarUrl(name); }
    var uname = $("#homeUserName");
    if (uname) uname.textContent = name;
    var utype = $("#homeUserType");
    if (utype) utype.textContent = acc && acc.type === "microsoft" ? t("accounts.microsoftType") : t("accounts.offline");

    var inst = currentInstance();
    var title = $("#homeTitle");
    var meta = $("#homeMeta");
    var launchBtn = $("#launchBtn");
    var switchBtn = $(".switch-version");
    var launchLabel = launchBtn ? launchBtn.querySelector("span") : null;

    if (title) title.textContent = inst ? (inst.display_name || inst.id) : "Paradise Island";
    if (meta) {
      meta.innerHTML = "";
      if (inst) {
        var chips = [
          '<span class="chip accent">' + escapeHtml(inst.id) + "</span>",
          '<span class="chip">' + escapeHtml(typeLabel(inst.type)) + "</span>",
          '<span class="chip">' + escapeHtml(loaderLabel(inst.loader)) + "</span>",
          '<span class="chip">' + escapeHtml(t("home.mods")) + " " + (inst.mod_count || 0) + "</span>",
          '<span class="chip">' + escapeHtml(inst.last_launched ? t("home.lastPlayed") + " · " + formatTime(inst.last_launched) : t("home.never")) + "</span>"
        ];
        meta.innerHTML = chips.join("");
      } else {
        meta.innerHTML = '<span class="chip">' + escapeHtml(t("home.noVersions")) + "</span>";
      }
    }
    if (launchBtn) {
      launchBtn.disabled = false;
      if (inst) {
        launchBtn.setAttribute("data-action", "launch");
        if (launchLabel) launchLabel.textContent = t("home.launch");
      } else {
        launchBtn.setAttribute("data-action", "goto-install");
        if (launchLabel) launchLabel.textContent = t("home.goInstall");
      }
    }
    if (switchBtn) switchBtn.classList.toggle("hidden", !inst);
    var foot = $("#homeFoot");
    if (foot) {
      foot.textContent = "Paradise Island Launcher" + (inst ? " · " + inst.id : "");
    }
  }

  /* ---------------- rendering: instances ---------------- */

  function filteredInstances() {
    var list = state.instances.filter(function (i) { return i.installed; });
    if (state.filter !== "all") list = list.filter(function (i) { return (i.loader || "vanilla") === state.filter; });
    if (state.search) {
      var q = state.search.toLowerCase();
      list = list.filter(function (i) {
        return (i.id || "").toLowerCase().indexOf(q) !== -1 ||
          (i.display_name || "").toLowerCase().indexOf(q) !== -1;
      });
    }
    list.sort(function (a, b) {
      if (state.sort === "recent") return (b.last_launched || 0) - (a.last_launched || 0);
      return String(a.display_name || a.id).localeCompare(String(b.display_name || b.id), state.lang);
    });
    return list;
  }

  function renderFilters() {
    var box = $("#instanceFilters");
    if (!box) return;
    var items = [
      { value: "all", label: t("filter.all") },
      { value: "vanilla", label: loaderLabel("vanilla") },
      { value: "forge", label: "Forge" },
      { value: "fabric", label: "Fabric" },
      { value: "quilt", label: "Quilt" },
      { value: "neoforge", label: "NeoForge" }
    ];
    box.innerHTML = "";
    items.forEach(function (item) {
      var b = document.createElement("button");
      b.className = "filter-chip" + (state.filter === item.value ? " active" : "");
      b.textContent = item.label;
      b.addEventListener("click", function () { state.filter = item.value; renderFilters(); renderInstances(); });
      box.appendChild(b);
    });
  }

  function instanceCard(inst) {
    var card = document.createElement("div");
    card.className = "instance-card";
    card.setAttribute("data-id", inst.id);
    card.innerHTML =
      '<img class="instance-icon" src="/api/instance/icon/' + encodeURIComponent(inst.id) + '?t=' + Date.now() + '" alt="">' +
      '<div class="instance-info">' +
        '<div class="instance-name">' + escapeHtml(inst.display_name || inst.id) + "</div>" +
        '<div class="instance-meta">' +
          '<span class="badge">' + escapeHtml(loaderLabel(inst.loader)) + "</span>" +
          "<span>" + escapeHtml(inst.id) + "</span>" +
          (inst.mod_count ? "<span>· " + (inst.mod_count) + " " + escapeHtml(t("home.mods")) + "</span>" : "") +
        "</div>" +
      "</div>" +
      '<div class="card-actions">' +
        '<button class="mini-btn" data-act="play" title="' + escapeHtml(t("instances.play")) + '"><svg><use href="#i-play"/></svg></button>' +
        '<button class="mini-btn" data-act="folder" title="' + escapeHtml(t("instances.folder")) + '"><svg><use href="#i-folder"/></svg></button>' +
        '<button class="mini-btn" data-act="more" title="' + escapeHtml(t("instances.more")) + '"><svg><use href="#i-list"/></svg></button>' +
      "</div>";
    var img = $(".instance-icon", card);
    attachImageFallback(img, "/static/images/icon.png");
    card.addEventListener("click", function (e) {
      var btn = e.target.closest ? e.target.closest("[data-act]") : null;
      if (btn) {
        e.stopPropagation();
        var act = btn.getAttribute("data-act");
        if (act === "play") launch(inst.id);
        else if (act === "folder") openFolder(inst.id);
        else showCtx(btn.getBoundingClientRect().left - 120, btn.getBoundingClientRect().bottom + 6, inst);
        return;
      }
      launch(inst.id);
    });
    card.addEventListener("contextmenu", function (e) {
      e.preventDefault();
      showCtx(e.clientX, e.clientY, inst);
    });
    return card;
  }

  function renderInstances() {
    var grid = $("#instancesGrid");
    if (!grid) return;
    grid.innerHTML = "";
    var list = filteredInstances();
    if (!list.length) {
      var empty = document.createElement("div");
      empty.className = "empty-state";
      empty.style.gridColumn = "1 / -1";
      empty.innerHTML =
        '<img src="/static/images/icon.png" alt="">' +
        '<div class="title">' + escapeHtml(state.instances.length ? t("instances.noResult") : t("instances.empty")) + "</div>" +
        '<div class="hint">' + escapeHtml(t("instances.emptyHint")) + "</div>";
      grid.appendChild(empty);
      return;
    }
    list.forEach(function (inst) { grid.appendChild(instanceCard(inst)); });
  }

  /* ---------------- rendering: accounts ---------------- */

  function renderAccounts() {
    var acc = activeAccount();
    var name = acc ? acc.name : (state.config.last_username || "Steve");
    var face = $("#skinFace");
    if (face) {
      attachImageFallback(face, "/static/images/avatar.png");
      face.src = avatarUrl(name);
    }
    var body = $("#skinBody");
    if (body) {
      body.onerror = function () { body.onerror = null; body.style.display = "none"; };
      body.src = bodyUrl(name);
      body.style.display = "block";
    }
    var skinName = $("#skinName");
    if (skinName) skinName.textContent = name;
    var skinType = $("#skinType");
    if (skinType) skinType.textContent = acc ? (acc.type === "microsoft" ? t("accounts.microsoftType") : t("accounts.offline")) : t("accounts.offline");

    var list = $("#accountList");
    if (!list) return;
    list.innerHTML = "";
    if (!state.accounts.length) {
      var empty = document.createElement("div");
      empty.className = "muted";
      empty.textContent = t("accounts.empty");
      list.appendChild(empty);
    } else {
      state.accounts.forEach(function (a) {
        var row = document.createElement("div");
        row.className = "account-item" + (a.uuid === state.active ? " active" : "");
        row.innerHTML =
          '<img class="account-avatar" alt="">' +
          '<div class="account-text">' +
            '<div class="account-name">' + escapeHtml(a.name) + "</div>" +
            '<div class="account-type">' + escapeHtml(a.type === "microsoft" ? t("accounts.microsoftType") : t("accounts.offline")) + "</div>" +
          "</div>";
        var img = $(".account-avatar", row);
        attachImageFallback(img, "/static/images/avatar.png");
        img.src = avatarUrl(a.name);
        if (a.uuid === state.active) {
          var tag = document.createElement("span");
          tag.className = "badge";
          tag.textContent = t("java.using");
          row.appendChild(tag);
        } else {
          var useBtn = makeButton(t("accounts.switch"), "ghost sm", function () { setActiveAccount(a.uuid); });
          row.appendChild(useBtn);
        }
        var del = makeButton(t("accounts.logout"), "ghost sm", function () { logoutAccount(a); });
        row.appendChild(del);
        list.appendChild(row);
      });
    }
    var hint = $("#msClientIdHint");
    if (hint) {
      var hasId = !!(state.config.microsoft_client_id || "").trim();
      hint.textContent = hasId ? "" : t("accounts.clientIdHint");
    }
  }

  /* ---------------- rendering: java ---------------- */

  function renderJava() {
    var list = $("#javaList");
    if (!list) return;
    list.innerHTML = "";
    if (!state.java.length) {
      var empty = document.createElement("div");
      empty.className = "muted";
      empty.textContent = t("java.none");
      list.appendChild(empty);
      return;
    }
    var current = (state.config.java_path || "").trim();
    state.java.forEach(function (j) {
      var row = document.createElement("div");
      row.className = "java-item";
      var major = j.major ? "Java " + j.major : "Java";
      row.innerHTML =
        '<div class="java-badge">' + escapeHtml(j.major ? String(j.major) : "?") + "</div>" +
        '<div class="java-main">' +
          '<div class="java-title">' + escapeHtml(major) +
            (j.version ? '<span class="tag">' + escapeHtml(j.version) + "</span>" : "") +
            '<span class="tag">' + escapeHtml(j.source === "launcher" ? t("java.sourceLauncher") : t("java.sourceSystem")) + "</span>" +
          "</div>" +
          '<div class="java-path">' + escapeHtml(j.path) + "</div>" +
        "</div>";
      var isCurrent = current && current.toLowerCase() === String(j.path).toLowerCase();
      if (isCurrent) {
        var badge = document.createElement("span");
        badge.className = "badge";
        badge.textContent = t("java.using");
        row.appendChild(badge);
      } else {
        var btn = makeButton(t("java.use"), "ghost sm", function () {
          post("/api/config", { java_path: j.path }).then(function (res) {
            if (res.ok) { state.config = res.config; toast(t("toast.javaSet"), "success"); renderJava(); }
          });
        });
        row.appendChild(btn);
      }
      list.appendChild(row);
    });
  }

  /* ---------------- rendering: settings ---------------- */

  function renderSettingsValues() {
    var set = function (id, value) {
      var el = $(id);
      if (!el) return;
      el.value = value == null ? "" : value;
    };
    set("#memInput", state.config.max_memory || 4096);
    set("#minMemInput", state.config.min_memory || 512);
    set("#javaInput", state.config.java_path || "");
    set("#msClientInput", state.config.microsoft_client_id || "");
    set("#jvmArgsInput", state.config.jvm_args || "");
    var iso = $("#isoSwitch");
    if (iso) iso.classList.toggle("on", !!state.config.version_isolation);
    var autoLog = $("#autoLogSwitch");
    if (autoLog) autoLog.classList.toggle("on", !!state.config.auto_open_log);
    var aboutVersion = $("#aboutVersion");
    if (aboutVersion) aboutVersion.textContent = "v" + (state.meta.version || "2.3") + (state.meta.frozen ? " (exe)" : "");
    var dataDir = $("#aboutDataDir");
    if (dataDir) dataDir.textContent = state.meta.data_dir || "";
    var redirect = $("#redirectHint");
    if (redirect) redirect.textContent = t("accounts.redirect") + ": http://127.0.0.1:" + (state.meta.port || 10131) + "/api/auth/microsoft/callback";
    var build = $("#buildTag");
    if (build) build.textContent = "v" + (state.meta.version || "2.3");
    var homeBuild = $("#homeBuild");
    if (homeBuild) homeBuild.textContent = "v" + (state.meta.version || "2.3");
  }

  function renderBackgroundChoices() {
    var box = $("#bgList");
    if (!box) return;
    box.innerHTML = "";
    state.backgrounds.forEach(function (b) {
      var el = document.createElement("div");
      el.className = "bg-item" + (Number(state.config.current_background || 0) === b.id ? " active" : "");
      el.style.backgroundImage = 'url("' + b.url + '")';
      var label = document.createElement("span");
      label.textContent = b.name === "custom" ? t("bg.custom") : (b.name === "default" ? t("bg.default") : t("bg.n", { n: b.id }));
      el.appendChild(label);
      el.addEventListener("click", function () {
        post("/api/config", { current_background: b.id }).then(function (res) {
          if (!res.ok) return;
          state.config = res.config;
          state.currentBg = b.id;
          renderBackgroundChoices();
          renderHome();
          toast(t("toast.bgUpdated"), "success");
        });
      });
      box.appendChild(el);
    });
  }

  function renderAll() {
    renderHome();
    renderFilters();
    renderInstances();
    renderAccounts();
    renderJava();
    renderSettingsValues();
    renderBackgroundChoices();
  }

  /* ---------------- data loading ---------------- */

  function loadConfig() {
    return api("/api/config").then(function (res) {
      state.meta = res;
      state.config = res.config || {};
      state.lang = state.config.language || "zh-CN";
      if (!window.I18N || !window.I18N[state.lang]) state.lang = "en";
    });
  }

  function loadAccounts() {
    return api("/api/auth/accounts").then(function (res) {
      if (!res.ok) return;
      state.accounts = res.accounts || [];
      state.active = res.active || "";
      renderAccounts();
      renderHome();
    });
  }

  function loadInstances() {
    return api("/api/instances").then(function (res) {
      if (!res.ok) return;
      state.instances = res.instances || [];
      if (!currentInstance()) {
        var installed = state.instances.filter(function (i) { return i.installed; });
        var last = state.config.last_version;
        var match = installed.filter(function (i) { return i.id === last; })[0];
        state.selected = match ? match.id : (installed[0] ? installed[0].id : "");
      }
      renderInstances();
      renderHome();
    });
  }

  function loadVersions() {
    return api("/api/versions").then(function (res) {
      if (!res.ok) {
        toast(res.error || t("toast.failed"), "error");
        state.versions = [];
        return;
      }
      state.versions = res.versions || [];
      if (!state.installVersion) {
        var firstInstalled = state.versions.filter(function (v) { return v.installed; })[0];
        state.installVersion = firstInstalled ? firstInstalled.id : (state.versions[0] ? state.versions[0].id : "");
      }
      updateInstallLabel();
    });
  }

  function loadJava() {
    return api("/api/java/list").then(function (res) {
      if (!res.ok) return;
      state.java = res.installed || [];
      renderJava();
    });
  }

  function loadBackgrounds() {
    return api("/api/backgrounds").then(function (res) {
      if (!res.ok) return;
      state.backgrounds = res.backgrounds || [];
      state.currentBg = res.current || 0;
      renderBackgroundChoices();
      renderHome();
    });
  }

  /* ---------------- actions ---------------- */

  function go(page) {
    state.page = page;
    $$(".page").forEach(function (p) { p.classList.toggle("active", p.id === "page-" + page); });
    $$(".nav-item").forEach(function (b) { b.classList.toggle("active", b.getAttribute("data-page") === page); });
    try { history.replaceState(null, "", "#" + page); } catch (e) { /* ignore */ }
    if (page === "java") loadJava();
    if (page === "accounts") loadAccounts();
    if (page === "settings") { renderSettingsValues(); loadBackgrounds(); }
  }

  function openInstallPanel(open) {
    var panel = $("#installPanel");
    if (!panel) return;
    if (open === true) panel.classList.remove("hidden");
    else if (open === false) panel.classList.add("hidden");
    else panel.classList.toggle("hidden");
    if (!panel.classList.contains("hidden")) updateInstallLabel();
  }

  function updateInstallLabel() {
    var label = $("#versionPickLabel");
    if (label) label.textContent = state.installVersion || t("common.none");
  }

  function startInstall() {
    if (!state.installVersion) {
      toast(t("toast.noVersions"), "error");
      openVersionPicker("install");
      return;
    }
    var loader = $("#loaderSelect") ? $("#loaderSelect").value : "vanilla";
    var btn = $("#installBtn");
    if (btn) btn.disabled = true;
    post("/api/install", { version: state.installVersion, loader: loader }).then(function (res) {
      if (!res.ok) {
        if (btn) btn.disabled = false;
        toast(res.error || t("instances.installFailed"), "error");
        return;
      }
      toast(t("toast.installStarted"), "success");
      startProgress("install");
    }).catch(function (err) {
      if (btn) btn.disabled = false;
      toast(String(err), "error");
    });
  }

  function launch(vid) {
    var id = vid || state.selected;
    if (!id) {
      var installed = state.instances.filter(function (i) { return i.installed; });
      if (installed.length) return launch(installed[0].id);
      toast(t("toast.noVersions"), "error");
      go("instances");
      return;
    }
    state.selected = id;
    renderHome();
    var btn = $("#launchBtn");
    var label = btn ? btn.querySelector("span") : null;
    if (btn) { btn.disabled = true; if (label) label.textContent = t("home.launching"); }
    post("/api/launch", { version: id }).then(function (res) {
      if (btn) btn.disabled = false;
      if (label) label.textContent = t("home.launch");
      if (res.ok) {
        toast(t("toast.launched", { pid: res.pid }), "success");
        if (state.config.auto_open_log) openLog("instance", id);
        loadInstances();
      } else {
        showError(t("toast.launchFailed"), res.error);
      }
    }).catch(function (err) {
      if (btn) btn.disabled = false;
      if (label) label.textContent = t("home.launch");
      showError(t("toast.launchFailed"), String(err));
    });
  }

  function openFolder(vid) {
    post("/api/instance/open_folder", { version: vid }).then(function (res) {
      if (!res.ok) toast(res.error || t("toast.failed"), "error");
      else toast(t("toast.folderOpened"), "success");
    });
  }

  function openDataFolder() {
    post("/api/open_path", { kind: "minecraft" }).then(function (res) {
      if (!res.ok) toast(res.error || t("toast.failed"), "error");
      else toast(t("toast.folderOpened"), "success");
    });
  }

  function deleteInstance(inst) {
    confirmBox(t("instances.confirmDelete") + "\n" + inst.id, true).then(function (ok) {
      if (!ok) return;
      post("/api/instance/delete", { version: inst.id }).then(function (res) {
        if (!res.ok) return toast(res.error || t("toast.failed"), "error");
        toast(t("toast.deleted"), "success");
        if (state.selected === inst.id) state.selected = "";
        loadInstances();
        loadVersions();
      });
    });
  }

  function setActiveAccount(uuid) {
    post("/api/auth/set_active", { uuid: uuid }).then(function (res) {
      if (!res.ok) return toast(res.error || t("toast.failed"), "error");
      toast(t("toast.switched"), "success");
      loadAccounts(); loadInstances(); renderHome();
    });
  }

  function logoutAccount(acc) {
    post("/api/auth/logout", { uuid: acc.uuid }).then(function (res) {
      if (!res.ok) return toast(res.error || t("toast.failed"), "error");
      toast(t("toast.logout"), "success");
      loadAccounts(); loadInstances(); renderHome();
    });
  }

  function addOfflineAccount() {
    var input = $("#offlineName");
    var name = input ? input.value.trim() : "";
    if (!/^[A-Za-z0-9_]{3,16}$/.test(name)) return toast(t("accounts.invalidName"), "error");
    post("/api/auth/offline/add", { name: name }).then(function (res) {
      if (!res.ok) return toast(res.error || t("toast.failed"), "error");
      if (input) input.value = "";
      toast(t("toast.added"), "success");
      loadAccounts(); loadInstances(); renderHome();
    });
  }

  function saveSettings() {
    var data = {
      download_source: $("#sourceSelect") ? $("#sourceSelect").value : "bmclapi",
      version_isolation: $("#isoSwitch") ? $("#isoSwitch").classList.contains("on") : true,
      max_memory: parseInt(($("#memInput") || {}).value, 10) || 4096,
      min_memory: parseInt(($("#minMemInput") || {}).value, 10) || 512,
      java_path: $("#javaInput") ? $("#javaInput").value.trim() : "",
      jvm_args: $("#jvmArgsInput") ? $("#jvmArgsInput").value.trim() : "",
      microsoft_client_id: $("#msClientInput") ? $("#msClientInput").value.trim() : "",
      auto_open_log: $("#autoLogSwitch") ? $("#autoLogSwitch").classList.contains("on") : false,
      theme: state.config.theme || "dark",
      language: state.lang
    };
    post("/api/config", data).then(function (res) {
      if (!res.ok) return toast(res.error || t("toast.failed"), "error");
      state.config = res.config;
      toast(t("settings.saved"), "success");
      renderAll();
    });
  }

  function installJava() {
    var sel = $("#javaVersionSelect");
    var major = sel ? parseInt(sel.value, 10) : 17;
    post("/api/java/install", { major: major }).then(function (res) {
      if (!res.ok) return toast(res.error || t("java.failed"), "error");
      toast(t("java.downloading"), "success");
      startProgress("java");
    });
  }

  function uploadBackground(file) {
    if (!file) return;
    var fd = new FormData();
    fd.append("file", file);
    fetch("/api/background/upload", { method: "POST", body: fd })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (!res.ok) return toast(res.error || t("toast.failed"), "error");
        toast(t("toast.bgUpdated"), "success");
        loadBackgrounds();
      });
  }

  function resetBackground() {
    post("/api/background/reset", {}).then(function () {
      toast(t("toast.bgUpdated"), "success");
      loadBackgrounds();
    });
  }

  function quitLauncher() {
    confirmBox(t("settings.quitConfirm"), true).then(function (ok) {
      if (!ok) return;
      post("/api/quit", {}).then(function () {
        document.body.innerHTML = '<div style="height:100vh;display:flex;align-items:center;justify-content:center;color:#94a3b8;font-family:sans-serif">' +
          escapeHtml(t("toast.quit")) + "</div>";
      });
    });
  }

  /* ---------------- context menu ---------------- */

  function hideCtx() {
    var menu = $("#ctxMenu");
    if (menu) menu.classList.remove("show");
  }

  function showCtx(x, y, inst) {
    var menu = $("#ctxMenu");
    if (!menu) return;
    menu.innerHTML = "";
    var items = [
      { icon: "i-play", label: t("ctx.play"), action: function () { launch(inst.id); } },
      { icon: "i-folder", label: t("ctx.folder"), action: function () { openFolder(inst.id); } },
      { icon: "i-package", label: t("ctx.mods"), action: function () { openMods(inst.id); } },
      { icon: "i-edit", label: t("ctx.settings"), action: function () { openInstanceSettings(inst); } },
      { icon: "i-list", label: t("ctx.log"), action: function () { openLog("instance", inst.id); } },
      { sep: true },
      { icon: "i-trash", label: t("ctx.delete"), danger: true, action: function () { deleteInstance(inst); } }
    ];
    items.forEach(function (item) {
      if (item.sep) {
        var sep = document.createElement("div");
        sep.className = "ctx-sep";
        menu.appendChild(sep);
        return;
      }
      var row = document.createElement("div");
      row.className = "ctx-item" + (item.danger ? " danger" : "");
      row.innerHTML = '<svg><use href="#' + item.icon + '"/></svg><span>' + escapeHtml(item.label) + "</span>";
      row.addEventListener("click", function () { hideCtx(); item.action(); });
      menu.appendChild(row);
    });
    menu.classList.add("show");
    var rect = menu.getBoundingClientRect();
    var left = Math.min(x, window.innerWidth - rect.width - 10);
    var top = Math.min(y, window.innerHeight - rect.height - 10);
    menu.style.left = Math.max(8, left) + "px";
    menu.style.top = Math.max(8, top) + "px";
  }

  /* ---------------- version picker ---------------- */

  function openVersionPicker(mode) {
    var body = document.createElement("div");
    var search = document.createElement("input");
    search.className = "input";
    search.placeholder = t("instances.searchVersion");
    var list = document.createElement("div");
    list.className = "version-list";
    body.appendChild(search);
    body.appendChild(list);

    function render() {
      var q = search.value.trim().toLowerCase();
      list.innerHTML = "";
      var items = [];
      if (mode === "install") {
        items = state.versions.filter(function (v) { return !q || v.id.toLowerCase().indexOf(q) !== -1; });
        if (items.length > 400) items = items.slice(0, 400);
      } else {
        items = state.instances.filter(function (v) { return v.installed; })
          .filter(function (v) { return !q || v.id.toLowerCase().indexOf(q) !== -1; });
      }
      if (!items.length) {
        var empty = document.createElement("div");
        empty.className = "muted";
        empty.textContent = t("instances.noResult");
        list.appendChild(empty);
        return;
      }
      items.forEach(function (v) {
        var row = document.createElement("div");
        var selected = mode === "install" ? v.id === state.installVersion : v.id === state.selected;
        row.className = "version-row" + (selected ? " selected" : "");
        row.innerHTML =
          (mode === "instance" ? '<img src="/api/instance/icon/' + encodeURIComponent(v.id) + '?t=' + Date.now() + '" alt="">' : "") +
          '<div><div class="vname">' + escapeHtml(v.id) + "</div>" +
          '<div class="vmeta">' + escapeHtml(mode === "install" ? typeLabel(v.type) : loaderLabel(v.loader)) +
          (v.installed ? " · " + escapeHtml(t("instances.installed")) : "") + "</div></div>" +
          '<span class="vcheck">' + (selected ? '<svg style="width:15px;height:15px"><use href="#i-check"/></svg>' : "") + "</span>";
        row.addEventListener("click", function () {
          if (mode === "install") {
            state.installVersion = v.id;
            updateInstallLabel();
          } else {
            state.selected = v.id;
            renderHome();
          }
          closeModal();
        });
        list.appendChild(row);
      });
    }

    var timer = null;
    search.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(render, 120);
    });
    render();
    openModal({
      title: mode === "install" ? t("instances.install") : t("home.switchVersion"),
      body: body,
      wide: true,
      footer: [makeButton(t("common.close"), "ghost", closeModal)]
    });
    setTimeout(function () { search.focus(); }, 60);
  }

  /* ---------------- instance settings ---------------- */

  function openInstanceSettings(inst) {
    var body = document.createElement("div");
    var current = state.config;
    body.innerHTML =
      '<div class="field"><label>' + escapeHtml(t("inst.name")) + '</label>' +
        '<input class="input" id="msName" maxlength="48" value="' + escapeHtml(inst.display_name || inst.id) + '"></div>' +
      '<div class="field"><label>' + escapeHtml(t("inst.memory")) + '</label>' +
        '<input class="input" id="msMemory" type="number" min="512" step="512" placeholder="' + escapeHtml(current.max_memory || 4096) + '" value="' + escapeHtml(inst.max_memory || "") + '"></div>' +
      '<div class="field"><label>' + escapeHtml(t("inst.jvm")) + '</label>' +
        '<input class="input" id="msJvm" placeholder="-XX:+UseG1GC" value="' + escapeHtml(inst.jvm_args || "") + '"></div>' +
      '<div class="field"><label>' + escapeHtml(t("inst.java")) + '</label>' +
        '<input class="input" id="msJava" placeholder="auto" value="' + escapeHtml(inst.java_path || "") + '"></div>' +
      '<div class="setting-row" style="border:0;padding:4px 0"><div class="setting-name">' + escapeHtml(t("inst.isolation")) + '</div>' +
        '<div class="switch' + (inst.isolated ? " on" : "") + '" id="msIso"></div></div>' +
      '<div class="setting-row" style="border:0;padding:10px 0 0"><div class="setting-name">' + escapeHtml(t("inst.icon")) + "</div>" +
        '<div class="row"><button class="btn ghost sm" id="msIconBtn"><svg><use href="#i-image"/></svg>' + escapeHtml(t("settings.upload")) + "</button>" +
        '<button class="btn ghost sm" id="msIconReset">' + escapeHtml(t("settings.resetBg")) + "</button></div></div>" +
      '<div class="mt8"><img id="msIconPreview" src="/api/instance/icon/' + encodeURIComponent(inst.id) + '?t=' + Date.now() + '" style="width:64px;height:64px;border-radius:14px" alt=""></div>';

    var iso = $("#msIso", body);
    iso.addEventListener("click", function () { iso.classList.toggle("on"); });

    var iconBtn = $("#msIconBtn", body);
    iconBtn.addEventListener("click", function () {
      var input = document.createElement("input");
      input.type = "file";
      input.accept = "image/png,image/jpeg";
      input.onchange = function () {
        if (!input.files[0]) return;
        var fd = new FormData();
        fd.append("version", inst.id);
        fd.append("file", input.files[0]);
        fetch("/api/instance/icon/upload", { method: "POST", body: fd })
          .then(function (r) { return r.json(); })
          .then(function (res) {
            if (!res.ok) return toast(res.error || t("toast.failed"), "error");
            var preview = $("#msIconPreview", body);
            if (preview) preview.src = "/api/instance/icon/" + encodeURIComponent(inst.id) + "?t=" + Date.now();
            toast(t("toast.bgUpdated"), "success");
            loadInstances();
          });
      };
      input.click();
    });

    $("#msIconReset", body).addEventListener("click", function () {
      post("/api/instance/icon/reset", { version: inst.id }).then(function (res) {
        if (!res.ok) return toast(res.error || t("toast.failed"), "error");
        var preview = $("#msIconPreview", body);
        if (preview) preview.src = "/api/instance/icon/" + encodeURIComponent(inst.id) + "?t=" + Date.now();
        loadInstances();
      });
    });

    function save() {
      var data = {
        display_name: $("#msName", body).value.trim() || inst.id,
        max_memory: parseInt($("#msMemory", body).value, 10) || null,
        jvm_args: $("#msJvm", body).value.trim(),
        java_path: $("#msJava", body).value.trim() || null,
        version_isolation: iso.classList.contains("on")
      };
      post("/api/instance/settings/" + encodeURIComponent(inst.id), data).then(function (res) {
        if (!res.ok) return toast(res.error || t("toast.failed"), "error");
        toast(t("inst.saved"), "success");
        closeModal();
        loadInstances();
      });
    }

    openModal({
      title: t("inst.title") + " · " + inst.id,
      body: body,
      footer: [
        makeButton(t("common.cancel"), "ghost", closeModal),
        makeButton(t("common.save"), "primary", save)
      ]
    });
  }

  /* ---------------- mods ---------------- */

  function openMods(vid) {
    var body = document.createElement("div");
    var listBox = document.createElement("div");
    listBox.className = "mod-list";
    var drop = document.createElement("div");
    drop.className = "drop-zone";
    drop.textContent = t("mods.hint");
    body.appendChild(drop);
    body.appendChild(listBox);

    function refresh() {
      api("/api/instance/mods?version=" + encodeURIComponent(vid)).then(function (res) {
        if (!res.ok) {
          listBox.innerHTML = '<div class="muted">' + escapeHtml(res.error || "") + "</div>";
          return;
        }
        listBox.innerHTML = "";
        if (!res.mods.length) {
          var empty = document.createElement("div");
          empty.className = "muted";
          empty.textContent = t("mods.empty");
          listBox.appendChild(empty);
          return;
        }
        res.mods.forEach(function (m) {
          var row = document.createElement("div");
          row.className = "mod-item" + (m.enabled ? "" : " disabled");
          row.innerHTML =
            '<div class="mod-icon"><svg><use href="#i-package"/></svg></div>' +
            '<div class="mod-main"><div class="mod-name">' + escapeHtml(m.name) + "</div>" +
            '<div class="mod-size">' + formatBytes(m.size) + (m.enabled ? "" : " · " + escapeHtml(t("mods.disabledTag"))) + "</div></div>";
          var toggle = makeButton(m.enabled ? t("mods.disable") : t("mods.enable"), "ghost sm", function () {
            post("/api/instance/mods/toggle", { version: vid, name: m.name }).then(function (r) {
              if (!r.ok) return toast(r.error || t("toast.failed"), "error");
              toast(t("mods.toggled"), "success");
              refresh();
            });
          });
          var del = makeButton(t("mods.delete"), "ghost sm", function () {
            confirmBox(t("mods.confirmDelete") + "\n" + m.name, true).then(function (ok) {
              if (!ok) return;
              post("/api/instance/mods/delete", { version: vid, name: m.name }).then(function (r) {
                if (!r.ok) return toast(r.error || t("toast.failed"), "error");
                toast(t("mods.deleted"), "success");
                refresh();
              });
            });
          });
          row.appendChild(toggle);
          row.appendChild(del);
          listBox.appendChild(row);
        });
        loadInstances();
      });
    }

    function upload(files) {
      if (!files || !files.length) return;
      var fd = new FormData();
      fd.append("version", vid);
      for (var i = 0; i < files.length; i++) fd.append("files", files[i]);
      fetch("/api/instance/mods/import", { method: "POST", body: fd })
        .then(function (r) { return r.json(); })
        .then(function (res) {
          if (!res.ok) return toast(res.error || t("toast.failed"), "error");
          toast(t("mods.imported", { n: res.saved }), "success");
          refresh();
        });
    }

    drop.addEventListener("click", function () {
      var input = document.createElement("input");
      input.type = "file";
      input.accept = ".jar";
      input.multiple = true;
      input.onchange = function () { upload(input.files); };
      input.click();
    });
    ["dragenter", "dragover"].forEach(function (ev) {
      drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add("over"); });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove("over"); });
    });
    drop.addEventListener("drop", function (e) {
      if (e.dataTransfer && e.dataTransfer.files) upload(e.dataTransfer.files);
    });

    refresh();
    openModal({
      title: t("mods.title") + " · " + vid,
      body: body,
      wide: true,
      footer: [
        makeButton(t("mods.import"), "primary", function () {
          var input = document.createElement("input");
          input.type = "file";
          input.accept = ".jar";
          input.multiple = true;
          input.onchange = function () { upload(input.files); };
          input.click();
        }),
        makeButton(t("common.close"), "ghost", closeModal)
      ]
    });
  }

  /* ---------------- log ---------------- */

  function stopLogAuto() {
    if (state.logTimer) {
      clearInterval(state.logTimer);
      state.logTimer = null;
    }
  }

  function openLog(source, vid) {
    state.logSource = source || "launcher";
    state.logVid = vid || "";
    if (state.logSource === "instance" && !state.logVid) state.logSource = "launcher";
    var body = document.createElement("div");
    var pre = document.createElement("div");
    pre.className = "log-box";
    pre.id = "logBox";
    body.appendChild(pre);

    function fetchLog() {
      var url = state.logSource === "instance"
        ? "/api/instance/log?version=" + encodeURIComponent(state.logVid)
        : "/api/log";
      api(url).then(function (res) {
        if (!res.ok) {
          pre.textContent = res.error || "";
          return;
        }
        if (res.fallback && state.logSource === "instance") {
          $("#modalTitle").textContent = t("log.launcher") + (state.logVid ? " · " + state.logVid : "");
        }
        var atBottom = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 40;
        if (!res.text) {
          pre.textContent = t("log.empty");
          return;
        }
        pre.textContent = res.text;
        if (state.logAutoScroll || atBottom) pre.scrollTop = pre.scrollHeight;
      }).catch(function () { /* ignore */ });
    }

    var footer = [
      makeButton(t("common.copy"), "ghost", function () {
        var text = pre.textContent || "";
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(function () { toast(t("toast.copied"), "success"); });
        } else {
          var ta = document.createElement("textarea");
          ta.value = text;
          document.body.appendChild(ta);
          ta.select();
          try { document.execCommand("copy"); toast(t("toast.copied"), "success"); } catch (e) {}
          document.body.removeChild(ta);
        }
      }),
      makeButton(t("common.refresh"), "ghost", fetchLog)
    ];
    if (state.logSource === "launcher") {
      footer.push(makeButton(t("log.openFile"), "ghost", function () {
        post("/api/open_path", { kind: "logfile" });
      }));
    }
    footer.push(makeButton(t("common.close"), "primary", closeModal));

    fetchLog();
    stopLogAuto();
    state.logTimer = setInterval(fetchLog, 2000);
    openModal({
      title: (state.logSource === "instance" ? t("log.game") : t("log.launcher")) + (state.logVid ? " · " + state.logVid : ""),
      body: body,
      wide: true,
      footer: footer
    });
  }

  /* ---------------- progress ---------------- */

  function stageText(p) {
    var label = t("stage." + (p.stage || "prepare"));
    if (label === "stage." + (p.stage || "prepare")) label = t("stage.prepare");
    if (p.status === "error") {
      return t("stage.error") + (p.message ? ": " + p.message : "");
    }
    if (p.stage === "loader" && p.message) return label + " · " + p.message;
    if ((p.stage === "libraries" || p.stage === "assets") && p.message) return label + " " + p.message;
    if (p.status === "done" && p.message && p.message.indexOf("warn:") === 0) {
      return t("instances.installDone") + " (" + p.message.slice(5) + ")";
    }
    return label;
  }

  function updateProgressUI(kind, p) {
    var bar = kind === "java" ? $("#javaProgressBar") : $("#progressBar");
    var text = kind === "java" ? $("#javaProgressText") : $("#progressText");
    var pct = kind === "java" ? $("#javaProgressPercent") : $("#progressPercent");
    var percent = Math.max(0, Math.min(100, p.percent || 0));
    if (bar) bar.style.width = percent + "%";
    if (text) text.textContent = stageText(p);
    if (pct) pct.textContent = percent + "%";
  }

  function startProgress(kind) {
    stopProgress();
    state.progressKind = kind;
    var barWrap = kind === "java" ? $("#javaProgressBarWrap") : $("#progressBarWrap");
    var textWrap = kind === "java" ? $("#javaProgressTextWrap") : $("#progressTextWrap");
    if (barWrap) barWrap.classList.remove("hidden");
    if (textWrap) textWrap.classList.remove("hidden");
    if (kind === "install") {
      var btn = $("#installBtn");
      if (btn) btn.disabled = true;
    }
    var tick = function () {
      api("/api/progress").then(function (p) {
        updateProgressUI(kind, p);
        if (p.status !== "running") {
          stopProgress();
          onProgressFinished(kind, p);
        }
      }).catch(function () { /* keep polling */ });
    };
    tick();
    state.progressTimer = setInterval(tick, 700);
  }

  function stopProgress() {
    if (state.progressTimer) {
      clearInterval(state.progressTimer);
      state.progressTimer = null;
    }
  }

  function onProgressFinished(kind, p) {
    var btn = kind === "java" ? null : $("#installBtn");
    if (btn) btn.disabled = false;
    if (kind === "install") {
      if (p.status === "done") {
        toast(t("toast.installDone"), "success");
        loadInstances();
        loadVersions();
      } else if (p.status === "error") {
        toast(p.message || t("instances.installFailed"), "error");
      }
    } else {
      if (p.status === "done") {
        toast(t("java.done"), "success");
        loadJava();
        loadConfig().then(renderSettingsValues);
      } else if (p.status === "error") {
        toast(p.message || t("java.failed"), "error");
      }
    }
  }

  /* ---------------- event wiring ---------------- */

  var actions = {
    nav: function (el) { go(el.getAttribute("data-page")); },
    "toggle-theme": function () {
      var themes = ["dark", "light", "system"];
      var next = themes[(themes.indexOf(state.config.theme || "dark") + 1) % themes.length];
      applyTheme(next, true);
    },
    "toggle-install": function () { openInstallPanel(); },
    "refresh-instances": function () { loadInstances(); loadVersions(); toast(t("common.refresh"), "success"); },
    "pick-install-version": function () { openVersionPicker("install"); },
    install: function () { startInstall(); },
    "refresh-java": function () { loadJava(); },
    "install-java": function () { installJava(); },
    "save-settings": function () { saveSettings(); },
    "upload-bg": function () { var f = $("#bgFile"); if (f) f.click(); },
    "reset-bg": function () { resetBackground(); },
    "toggle-iso": function (el) { el.classList.toggle("on"); },
    "toggle-autolog": function (el) { el.classList.toggle("on"); },
    "open-log": function () { openLog("instance", state.selected); },
    "open-instance-folder": function () { if (state.selected) openFolder(state.selected); else toast(t("toast.noVersions"), "error"); },
    "open-data": function () { openDataFolder(); },
    "add-offline": function () { addOfflineAccount(); },
    "ms-login": function () { window.location.href = "/api/auth/microsoft/login"; },
    "pick-version": function () { openVersionPicker("instance"); },
    launch: function () { launch(); },
    "goto-install": function () {
      go("instances");
      var panel = $("#installPanel");
      if (panel) panel.classList.remove("hidden");
    },
    "close-modal": function () { closeModal(); },
    quit: function () { quitLauncher(); }
  };

  function handleAction(action, el) {
    if (actions[action]) actions[action](el);
  }

  function bindEvents() {
    document.addEventListener("click", function (e) {
      var el = e.target.closest ? e.target.closest("[data-action]") : null;
      if (!el) return;
      handleAction(el.getAttribute("data-action"), el);
    });

    $("#modalBg").addEventListener("click", function (e) {
      if (e.target === $("#modalBg")) closeModal();
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        if ($("#modalBg").classList.contains("show")) closeModal();
        else hideCtx();
      }
    });

    document.addEventListener("click", function (e) {
      if (!e.target.closest || !e.target.closest("#ctxMenu")) hideCtx();
    });
    window.addEventListener("resize", hideCtx);

    $("#instanceSearch").addEventListener("input", function (e) {
      state.search = e.target.value.trim();
      renderInstances();
    });
    $("#instanceSort").addEventListener("change", function (e) {
      state.sort = e.target.value;
      renderInstances();
    });
    $("#themeSelect").addEventListener("change", function (e) {
      applyTheme(e.target.value, true);
    });
    $("#languageSelect").addEventListener("change", function (e) {
      var lang = e.target.value;
      applyLanguage(lang);
      post("/api/config", { language: lang });
    });
    $("#sourceSelect").addEventListener("change", function (e) {
      post("/api/config", { download_source: e.target.value }).then(function (res) {
        if (res.ok) state.config = res.config;
      });
    });
    $("#bgFile").addEventListener("change", function (e) {
      if (e.target.files && e.target.files[0]) uploadBackground(e.target.files[0]);
      e.target.value = "";
    });
    $("#offlineName").addEventListener("keydown", function (e) {
      if (e.key === "Enter") addOfflineAccount();
    });
    if (window.matchMedia) {
      var mq = window.matchMedia("(prefers-color-scheme: dark)");
      var onChange = function () { if (state.config.theme === "system") applyTheme("system", false); };
      if (mq.addEventListener) mq.addEventListener("change", onChange);
      else if (mq.addListener) mq.addListener(onChange);
    }
    window.addEventListener("contextmenu", function (e) {
      if (e.target.closest && e.target.closest("input, textarea")) return;
      if (!e.target.closest || !e.target.closest(".instance-card")) e.preventDefault();
    });
  }

  /* ---------------- init ---------------- */

  function handleAuthQuery() {
    var params = new URLSearchParams(window.location.search);
    if (params.get("auth_success")) {
      toast(t("toast.loginOk"), "success");
      loadAccounts();
      window.history.replaceState({}, "", "/");
    }
    if (params.get("auth_error")) {
      toast(params.get("auth_error"), "error");
      window.history.replaceState({}, "", "/");
    }
  }

  function init() {
    bindEvents();
    loadConfig().then(function () {
      state.currentBg = state.config.current_background || 0;
      applyTheme(state.config.theme || "dark", false);
      applyLanguage(state.lang);
      return Promise.all([loadAccounts(), loadInstances(), loadBackgrounds(), loadJava()]);
    }).then(function () {
      loadVersions();
      api("/api/progress").then(function (p) {
        if (p.status === "running") startProgress(p.stage === "java" ? "java" : "install");
      });
      handleAuthQuery();
      var hash = (location.hash || "").replace("#", "");
      if (["home", "instances", "accounts", "java", "settings"].indexOf(hash) !== -1 && hash !== "home") go(hash);
      window.__PIL_READY = true;
    }).catch(function (err) {
      console.error("[PIL] init failed", err);
      toast(String(err), "error");
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
