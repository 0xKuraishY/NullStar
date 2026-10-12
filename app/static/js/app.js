/* NULLSTAR: console behaviours.
   Everything here is enhancement: the page is fully usable with JS off. */
(function () {
  "use strict";

  var $  = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };


  /* Dropdowns.

     Native selects cannot be styled past the closed state, so every one of
     them gets a listbox built next to it. The real select stays in the DOM and
     keeps the value, which means the form posts the same thing as before and
     nothing breaks with JavaScript turned off. */
  var tag = document.currentScript || document.querySelector('script[src*="app.js"]');
  var WORDS = {
    find: (tag && tag.dataset.wordFind) || "Filter",
    none: (tag && tag.dataset.wordNone) || "Nothing matches"
  };

  function buildPick(select) {
    if (select.multiple || select.dataset.plain === "1") return;

    var wrap = document.createElement("span");
    wrap.className = "pick" + (select.closest("table") ? " compact" : "");
    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(select);
    select.classList.add("native");
    select.setAttribute("tabindex", "-1");

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "pick-btn";
    btn.setAttribute("aria-haspopup", "listbox");
    btn.setAttribute("aria-expanded", "false");
    var near = wrap.parentNode ? wrap.parentNode.querySelector("label") : null;
    if (select.getAttribute("aria-label")) btn.setAttribute("aria-label", select.getAttribute("aria-label"));
    else if (near && near.textContent.trim()) btn.setAttribute("aria-label", near.textContent.trim());
    else if (select.name) btn.setAttribute("aria-label", select.name);
    btn.innerHTML = '<span class="lbl"></span><span class="arw"></span>';
    wrap.appendChild(btn);

    var menu = document.createElement("div");
    menu.className = "pick-menu";
    menu.setAttribute("role", "listbox");
    menu.hidden = true;
    wrap.appendChild(menu);

    var options = Array.prototype.map.call(select.options, function (o, i) {
      return { value: o.value, label: o.textContent.trim(), index: i };
    });
    var find = null;
    if (options.length > 12) {
      find = document.createElement("input");
      find.className = "pick-find";
      find.type = "text";
      find.setAttribute("placeholder", WORDS.find);
      menu.appendChild(find);
    }

    var list = document.createElement("div");
    menu.appendChild(list);
    var active = -1;

    function label() {
      var o = select.options[select.selectedIndex];
      btn.querySelector(".lbl").textContent = o ? o.textContent.trim() : "";
      btn.title = btn.querySelector(".lbl").textContent;
    }

    function paint(filter) {
      var q = (filter || "").toLowerCase();
      var shown = options.filter(function (o) {
        return !q || o.label.toLowerCase().indexOf(q) > -1;
      });
      list.innerHTML = "";
      if (!shown.length) {
        var none = document.createElement("div");
        none.className = "pick-none";
        none.textContent = WORDS.none;
        list.appendChild(none);
        active = -1;
        return;
      }
      shown.forEach(function (o, n) {
        var row = document.createElement("div");
        row.className = "pick-opt";
        row.setAttribute("role", "option");
        row.dataset.index = o.index;
        var chosen = o.index === select.selectedIndex;
        row.setAttribute("aria-selected", chosen ? "true" : "false");
        row.innerHTML = '<span class="tick"></span><span></span>';
        row.lastChild.textContent = o.label;

        if (n === 0) { row.classList.add("active"); active = 0; }
        list.appendChild(row);
      });
    }

    function rows() { return list.querySelectorAll(".pick-opt"); }

    function highlight(n) {
      var all = rows();
      if (!all.length) return;
      if (active > -1 && all[active]) all[active].classList.remove("active");
      active = (n + all.length) % all.length;
      all[active].classList.add("active");
      // not everywhere, and an exception here would abort the rest of open()
      if (all[active].scrollIntoView) all[active].scrollIntoView({ block: "nearest" });
    }

    function open() {
      document.querySelectorAll(".pick.open").forEach(function (other) {
        if (other !== wrap) close.call(other);
      });
      paint("");
      menu.hidden = false;
      wrap.classList.add("open");
      btn.setAttribute("aria-expanded", "true");
      var sel = list.querySelector('[aria-selected="true"]');
      if (sel) highlight(Array.prototype.indexOf.call(rows(), sel));
      if (find) { find.value = ""; find.focus(); }
    }

    function close() {
      var w = this instanceof Element ? this : wrap;
      var m = w.querySelector(".pick-menu");
      if (m) m.hidden = true;
      w.classList.remove("open");
      var b = w.querySelector(".pick-btn");
      if (b) b.setAttribute("aria-expanded", "false");
    }

    function choose(row) {
      if (!row) return;
      select.selectedIndex = parseInt(row.dataset.index, 10);
      label();
      close();
      btn.focus();
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }

    btn.addEventListener("click", function (ev) {
      ev.preventDefault();
      if (menu.hidden) open(); else close();
    });

    btn.addEventListener("keydown", function (ev) {
      if (ev.key === "ArrowDown" || ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        if (menu.hidden) open();
      }
    });

    list.addEventListener("click", function (ev) {
      choose(ev.target.closest(".pick-opt"));
    });

    menu.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") { ev.preventDefault(); close(); btn.focus(); }
      else if (ev.key === "ArrowDown") { ev.preventDefault(); highlight(active + 1); }
      else if (ev.key === "ArrowUp") { ev.preventDefault(); highlight(active - 1); }
      else if (ev.key === "Enter") { ev.preventDefault(); choose(rows()[active]); }
      else if (ev.key === "Tab") { close(); }
    });

    if (find) {
      find.addEventListener("input", function () { paint(find.value); });
    } else {
      // type a letter to jump, the way a real select does
      var typed = "", timer = null;
      menu.addEventListener("keydown", function (ev) {
        if (ev.key.length !== 1) return;
        typed += ev.key.toLowerCase();
        clearTimeout(timer);
        timer = setTimeout(function () { typed = ""; }, 700);
        var all = rows();
        for (var i = 0; i < all.length; i++) {
          if (all[i].textContent.trim().toLowerCase().indexOf(typed) === 0) {
            highlight(i);
            break;
          }
        }
      });
      menu.setAttribute("tabindex", "-1");
    }

    document.addEventListener("click", function (ev) {
      if (!wrap.contains(ev.target)) close();
    });

    label();
  }

  $$("select").forEach(buildPick);

  /* filter autosubmit */
  $$("[data-autosubmit]").forEach(function (form) {
    $$("select", form).forEach(function (el) {
      el.addEventListener("change", function () {
        var page = form.querySelector("input[name=page]");
        if (page) page.value = "1";
        form.submit();
      });
    });
  });

  /* ------------------------------------------------------------ copy / confirm */
  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-copy]");
    if (!btn) return;
    ev.preventDefault();
    var done = function () {
      var old = btn.textContent;
      btn.textContent = "copied";
      setTimeout(function () { btn.textContent = old; }, 1400);
    };
    if (navigator.clipboard) navigator.clipboard.writeText(btn.getAttribute("data-copy")).then(done, done);
    else done();
  });

  document.addEventListener("submit", function (ev) {
    var msg = ev.target.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) ev.preventDefault();
  });

  /* =========================================================== command palette
     Replaces a sidebar: every destination and filter is one keystroke away,
     which suits a feed you scan many times a day far better than a nav column. */
  var COMMANDS = [
    { k: "go",   t: "The wire",                 d: "g w", u: "/" },
    { k: "go",   t: "Buried treasure",          d: "g h", u: "/gems" },
    { k: "go",   t: "Big rooms",                d: "g m", u: "/majors" },
    { k: "go",   t: "First timers",             d: "g f", u: "/newcomers" },
    { k: "go",   t: "What you kept",            d: "g s", u: "/bookmarks" },
    { k: "go",   t: "The shape of it",          d: "g d", u: "/dashboard" },
    { k: "go",   t: "Your account and keys",    d: "",    u: "/account" },
    { k: "shop", t: "Workshop",                 d: "g o", u: "/admin" },
    { k: "shop", t: "Where it looks",           d: "",    u: "/admin/sources" },
    { k: "shop", t: "How it scores",            d: "",    u: "/admin/scoring" },
    { k: "shop", t: "Collector history",        d: "",    u: "/admin/runs" },
    { k: "shop", t: "People",                   d: "",    u: "/admin/users" },
    { k: "shop", t: "Invitations",              d: "",    u: "/admin/invites" },
    { k: "cut",  t: "Landed today",             d: "",    u: "/?window=24h&sort=new" },
    { k: "cut",  t: "Nobody has starred it",    d: "",    u: "/?max_stars=1&sort=score" },
    { k: "cut",  t: "Scoring eighty and up",    d: "",    u: "/?min_score=80" },
    { k: "cut",  t: "Exploit development",      d: "",    u: "/?category=exploit-dev" },
    { k: "cut",  t: "Offensive and red team",   d: "",    u: "/?category=offensive-security" },
    { k: "cut",  t: "Detection engineering",    d: "",    u: "/?category=detection-engineering" },
    { k: "cut",  t: "Malware analysis",         d: "",    u: "/?category=malware-analysis" },
    { k: "cut",  t: "Artificial intelligence security", d: "", u: "/?category=ai-security" },
    { k: "cut",  t: "Forensics and response",   d: "",    u: "/?category=dfir" },
    { k: "cut",  t: "Fuzzing",                  d: "",    u: "/?category=fuzzing" },
    { k: "cut",  t: "Cloud and containers",     d: "",    u: "/?category=cloud-security" }
  ];

  var pal = $("#pal"), palIn = $("#pal-input"), palList = $("#pal-list"), cur = 0, shown = [];

  function score(hay, needle) {
    hay = hay.toLowerCase();
    if (hay.indexOf(needle) === 0) return 3;
    if (hay.indexOf(needle) > -1) return 2;
    var i = 0;                                   // subsequence match: "hgm"  "hidden gems"
    for (var c = 0; c < hay.length && i < needle.length; c++) if (hay[c] === needle[i]) i++;
    return i === needle.length ? 1 : 0;
  }

  function renderPal(q) {
    q = (q || "").trim().toLowerCase();
    shown = !q ? COMMANDS.slice(0, 10)
      : COMMANDS.map(function (c) { return { c: c, s: score(c.k + " " + c.t, q) }; })
                .filter(function (x) { return x.s > 0; })
                .sort(function (a, b) { return b.s - a.s; })
                .map(function (x) { return x.c; }).slice(0, 10);

    if (q) shown.push({ k: "find", t: 'Search the wire for "' + q + '"', d: "enter", u: "/?q=" + encodeURIComponent(q) });

    if (!shown.length) { palList.innerHTML = '<div class="pal-empty">Nothing by that name.</div>'; return; }
    cur = 0;
    palList.innerHTML = shown.map(function (c, i) {
      return '<div class="pal-item" role="option" data-i="' + i + '" ' +
             (i === cur ? 'aria-selected="true"' : "") + '>' +
             '<span class="grp">' + c.k + "</span><span>" + c.t + "</span>" +
             (c.d ? '<span class="hint">' + c.d + "</span>" : "") + "</div>";
    }).join("");
  }

  function move(delta) {
    var items = $$(".pal-item", palList);
    if (!items.length) return;
    items[cur] && items[cur].removeAttribute("aria-selected");
    cur = (cur + delta + items.length) % items.length;
    items[cur].setAttribute("aria-selected", "true");
    items[cur].scrollIntoView({ block: "nearest" });
  }

  function openPal() { if (!pal) return; pal.hidden = false; palIn.value = ""; renderPal(""); palIn.focus(); }
  function closePal() { if (pal) pal.hidden = true; }

  if (pal) {
      $$("[data-pal-open]").forEach(function (b) { b.addEventListener("click", openPal); });
    palIn.addEventListener("input", function () { renderPal(palIn.value); });
    palIn.addEventListener("keydown", function (ev) {
      if (ev.key === "ArrowDown") { ev.preventDefault(); move(1); }
      else if (ev.key === "ArrowUp") { ev.preventDefault(); move(-1); }
      else if (ev.key === "Enter") { ev.preventDefault(); if (shown[cur]) window.location.href = shown[cur].u; }
      else if (ev.key === "Escape") closePal();
    });
    palList.addEventListener("click", function (ev) {
      var item = ev.target.closest(".pal-item");
      if (item) window.location.href = shown[item.getAttribute("data-i")].u;
    });
    pal.addEventListener("click", function (ev) { if (ev.target === pal) closePal(); });
  }

  /* ----------------------------------------------------------- shortcuts */
  var gPending = false;
  document.addEventListener("keydown", function (ev) {
    var tag = (ev.target.tagName || "").toLowerCase();
    var typing = tag === "input" || tag === "textarea" || tag === "select";

    if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === "k") { ev.preventDefault(); openPal(); return; }
    if (typing) { if (ev.key === "Escape") ev.target.blur(); return; }

    if (ev.key === "/" || ev.key === ":") { ev.preventDefault(); openPal(); return; }
    if (ev.key === "g") { gPending = true; setTimeout(function () { gPending = false; }, 800); return; }
    if (gPending) {
        var map = { w: "/", h: "/gems", m: "/majors", f: "/newcomers", s: "/bookmarks", d: "/dashboard", o: "/admin" };
      if (map[ev.key]) window.location.href = map[ev.key];
      gPending = false;
    }
  });

  /* =============================================================== live wire
     Server-sent events. New rows are held behind a counter rather than injected
     under the cursor: nothing should move while you are reading it. */
  var tape = $("#entries"), newbar = $("#arrivals"), newcount = $("#arrivals-n");
  var status = null, pulseEl = null, pulseText = null;
  var pending = [], es = null;

  function setWire(text, cls) {
    if (!status) return;
    status.textContent = text;
    status.style.color = cls || "";
  }

  function flushPending() {
    if (!tape || !pending.length) return;
    pending.reverse().forEach(function (html) {
      var tmp = document.createElement("div");
      tmp.innerHTML = html.trim();
      var node = tmp.firstElementChild;
      if (!node) return;
      if (tape.querySelector('[data-repo="' + node.getAttribute("data-repo") + '"]')) return;
      node.classList.add("fresh-in");
      tape.insertBefore(node, tape.firstChild);
    });
    pending = [];
    newbar.hidden = true;
  }

  function connect() {
    if (!tape || !window.EventSource) return;
    var toggle = $("#live-toggle");
    if (toggle && !toggle.checked) return;

    es = new EventSource("/stream");

    es.addEventListener("open", function () { setWire("The wire is open.", "var(--mint)"); });

    es.addEventListener("repo", function (ev) {
      try {
        var data = JSON.parse(ev.data);
        if (tape.querySelector('[data-repo="' + data.id + '"]')) return;
        pending.push(data.html);
        newcount.textContent = pending.length;
        newbar.hidden = false;
        if (pulseEl) {
          pulseEl.classList.add("hit");
          setTimeout(function () { pulseEl.classList.remove("hit"); }, 1200);
        }
      } catch (e) {}
    });

    es.addEventListener("pulse", function (ev) {
      try {
        var p = JSON.parse(ev.data);
        if (pulseEl) pulseEl.classList.toggle("on", !!p.running);
        if (pulseText) pulseText.textContent = p.running ? "gathering" : "resting";
      } catch (e) {}
    });

    es.addEventListener("error", function () {
      setWire("Lost the wire, trying again.", "var(--amber)");
    });
  }

  if (newbar) newbar.addEventListener("click", flushPending);

  var liveToggle = $("#live-toggle");
  if (liveToggle) {
    liveToggle.addEventListener("change", function () {
      if (liveToggle.checked) { connect(); }
      else if (es) { es.close(); es = null; setWire("Paused.", ""); }
    });
  }

  connect();
})();
