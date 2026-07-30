/* SurveyMind · Smart Insights screen (general data platform, batch 2)
 *
 * Self-contained data layer for #screen-insight. Deliberately independent of
 * data.js (whose state lives in its own closure): the session id is shared
 * through localStorage("sm_session"), everything else is fetched from the
 * platform endpoints (/mode, /semantics, /general-overview).
 *
 * Same constraints as data.js: the mockup's DOM/classes/tokens are the only
 * visual vocabulary; selects hide inside .sel chips; zh/en dual spans switch
 * via body[data-lang] with no refetch (the API returns both languages).
 */
(function () {
  "use strict";

  var API = (function () {
    var saved = "";
    try { saved = localStorage.getItem("sm_api") || ""; } catch (e) {}
    var configured = window.SURVEYMIND_CONFIG && window.SURVEYMIND_CONFIG.apiBaseUrl;
    var value = saved || configured || "";
    if (value) return String(value).replace(/\/+$/, "");
    var host = window.location.hostname;
    if (!host || host === "localhost" || host === "127.0.0.1") {
      return "http://127.0.0.1:8000";
    }
    return window.location.origin;
  })();

  var cache = { sessionId: null, mode: null, semantics: null, overview: null, loading: false };

  /* ---------- helpers (mirrors of data.js's private ones) ---------- */

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function api(path, opts) {
    return fetch(API + path, opts).then(function (r) {
      if (!r.ok) { return r.json().catch(function () { return {}; }).then(function (b) { throw new Error(b.detail || ("HTTP " + r.status)); }); }
      return r.json();
    });
  }

  function sessionId() {
    try { return localStorage.getItem("sm_session") || null; } catch (e) { return null; }
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function fmtInt(n) { return Number(n).toLocaleString("en-US"); }
  function fmtNum(n, d) {
    if (n === null || n === undefined || isNaN(n)) return "—";
    return Number(n).toFixed(d === undefined ? 1 : d).replace(/\.0+$/, "");
  }

  /* escape, then promote `backtick` field references to bold */
  function richText(s) {
    return esc(s).replace(/`([^`]+)`/g, "<b>$1</b>");
  }

  function chipSetValue(chip, zhText, enText) {
    Array.prototype.slice.call(chip.children).forEach(function (k) {
      if (k.classList.contains("lab") || k.classList.contains("car") || k.tagName === "SELECT") return;
      if (k.classList.contains("zh")) k.textContent = zhText;
      if (k.classList.contains("en")) k.textContent = enText;
    });
  }

  function chipEmbedSelect(chip, options, onChange) {
    var old = chip.querySelector("select");
    if (old) old.remove();
    var sel = document.createElement("select");
    sel.style.cssText = "position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:pointer;";
    options.forEach(function (o) {
      var opt = document.createElement("option");
      opt.value = o.value;
      opt.textContent = o.label;
      sel.appendChild(opt);
    });
    chip.style.position = "relative";
    sel.addEventListener("change", function () { onChange(sel.value); });
    chip.appendChild(sel);
    return sel;
  }

  /* ---------- vocabulary (wording matches src/i18n.py) ---------- */

  var ROLE_META = {
    numeric_metric:        { cls: "numeric",     zh: "数值指标",        en: "Numeric metric",  zhShort: "数值", enShort: "num" },
    categorical_dimension: { cls: "categorical", zh: "分类维度",        en: "Categorical",     zhShort: "分类", enShort: "cat" },
    datetime:              { cls: "datetime",    zh: "日期或时间",      zhShort: "日期", en: "Date / time",   enShort: "date" },
    identifier:            { cls: "id",          zh: "标识符或 ID",     zhShort: "ID",   en: "Identifier",    enShort: "id" },
    boolean:               { cls: "bool",        zh: "布尔变量",        zhShort: "布尔", en: "Boolean",       enShort: "bool" },
    free_text:             { cls: "text",        zh: "自由文本",        zhShort: "文本", en: "Free text",     enShort: "text" },
    multi_value:           { cls: "multi",       zh: "多值字段",        zhShort: "多值", en: "Multi-value",   enShort: "multi" },
    empty_or_constant:     { cls: "empty",       zh: "空白或不可用字段", zhShort: "空",   en: "Empty / const", enShort: "empty" },
  };

  var MODE_META = {
    general: { zh: "通用数据", en: "General data" },
    survey:  { zh: "问卷数据", en: "Survey data" },
    mixed:   { zh: "混合数据", en: "Mixed dataset" },
  };

  function roleMeta(role) {
    return ROLE_META[role] || { cls: "empty", zh: role, en: role, zhShort: role, enShort: role };
  }

  function roleBadge(role) {
    var m = roleMeta(role);
    return '<span class="rb ' + m.cls + '"><span class="d"></span><span class="zh">' + esc(m.zh) +
      '</span><span class="en">' + esc(m.en) + "</span></span>";
  }

  function dual(zhHTML, enHTML) {
    return '<span class="zh">' + zhHTML + '</span><span class="en">' + enHTML + "</span>";
  }

  /* ---------- rendering ---------- */

  function modeBody() { return $("#ins-mode-body"); }

  function showHint(zh, en) {
    var body = modeBody();
    if (body) {
      body.innerHTML = '<span style="font-size:12.5px;color:var(--muted);">' + dual(esc(zh), esc(en)) + "</span>";
    }
  }

  function showLoadError(err) {
    showHint("加载失败：" + (err && err.message ? err.message : "请求失败"),
      "Failed to load: " + (err && err.message ? err.message : "request failed"));
  }

  function renderMode() {
    var md = cache.mode;
    if (!md) return;
    var detected = md.detected, active = md.active;
    var dm = MODE_META[detected.mode] || { zh: detected.mode, en: detected.mode };

    var chip = $("#ins-mode-sel");
    if (chip) {
      var am = MODE_META[active] || { zh: active, en: active };
      chipSetValue(chip, am.zh, am.en);
      var sel = chipEmbedSelect(chip, [
        { value: "general", label: "通用数据 General" },
        { value: "survey", label: "问卷数据 Survey" },
        { value: "mixed", label: "混合数据 Mixed" },
      ], function (v) {
        api("/api/" + cache.sessionId + "/mode", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode: v }),
        }).then(function (res) {
          cache.mode = res;
          renderMode();
        }).catch(showLoadError);
      });
      sel.value = active;
    }

    var overrideNote = active !== detected.mode
      ? ' <span class="pill" style="font-size:11px;">' + dual("手动切换生效", "manual override") + "</span>"
      : "";
    var html =
      '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">' +
        '<span style="font-size:16px;font-weight:700;color:var(--ink);">' + dual("检测结果：" + esc(dm.zh), "Detected: " + esc(dm.en)) + "</span>" +
        '<span class="pill"><span class="sw" style="background:var(--t-scale-solid);"></span>' + dual("问卷特征 " + fmtNum(detected.survey_score, 2), "survey " + fmtNum(detected.survey_score, 2)) + "</span>" +
        '<span class="pill"><span class="sw" style="background:var(--accent);"></span>' + dual("通用特征 " + fmtNum(detected.general_score, 2), "general " + fmtNum(detected.general_score, 2)) + "</span>" +
        overrideNote +
      "</div>";
    if (detected.signals && detected.signals.length) {
      html += '<div class="legend">' + detected.signals.map(function (s) {
        return '<span class="pill mono" style="font-size:11px;color:var(--ink-3);">' + richText(s) + "</span>";
      }).join("") + "</div>";
    }
    var body = modeBody();
    if (body) body.innerHTML = html;
  }

  function renderMetrics() {
    var ov = cache.overview, sm = cache.semantics;
    if (!ov) return;
    var metrics = $all("#ins-metrics .metric");

    if (metrics[0]) $(".v", metrics[0]).textContent = fmtInt(ov.rows);

    if (metrics[1]) {
      $(".v", metrics[1]).textContent = ov.columns;
      var byRole = {};
      ((sm && sm.fields) || []).forEach(function (f) { byRole[f.role] = (byRole[f.role] || 0) + 1; });
      var zhParts = [], enParts = [];
      Object.keys(ROLE_META).forEach(function (role) {
        if (byRole[role]) {
          zhParts.push(roleMeta(role).zhShort + byRole[role]);
          enParts.push(byRole[role] + " " + roleMeta(role).enShort);
        }
      });
      $(".foot", metrics[1]).innerHTML = dual(esc(zhParts.join(" · ") || "—"), esc(enParts.join(" · ") || "—"));
    }

    if (metrics[2]) {
      $(".v", metrics[2]).innerHTML = fmtNum(ov.quality.overall_missing_pct, 1) + "<small>%</small>";
      var high = (ov.quality.high_missing || []).length;
      $(".foot", metrics[2]).innerHTML = high
        ? dual("缺失率超 10%：" + high + " 个字段", high + " field(s) above 10%")
        : dual("无高缺失字段", "no high-missing fields");
    }

    if (metrics[3]) {
      var dup = ov.quality.duplicate_rows;
      var v3 = $(".v", metrics[3]);
      v3.textContent = fmtInt(dup);
      v3.style.color = dup > 0 ? "var(--warn)" : "";
    }
  }

  var ROLE_OPTIONS = Object.keys(ROLE_META).map(function (role) {
    return { value: role, label: ROLE_META[role].zh + " " + ROLE_META[role].en };
  });

  function renderRoles() {
    var sm = cache.semantics;
    if (!sm) return;
    var tbody = $("#ins-role-table tbody");
    if (!tbody) return;

    tbody.innerHTML = sm.fields.map(function (f) {
      var evidence = (f.evidence || []).join("; ");
      var evShort = evidence.length > 42 ? evidence.slice(0, 42) + "…" : evidence;
      var missStyle = f.missing_pct > 10 ? ' style="color:var(--warn);font-weight:600"' : "";
      var m = roleMeta(f.role);
      return "<tr>" +
        '<td><b style="color:var(--ink)">' + esc(f.column) + "</b></td>" +
        "<td>" + roleBadge(f.role) + "</td>" +
        '<td class="mono" style="font-size:11px;color:var(--ink-3)" title="' + esc(evidence) + '">' + esc(evShort || "—") + "</td>" +
        '<td class="num-cell">' + fmtInt(f.non_null) + "</td>" +
        '<td class="num-cell">' + fmtInt(f.unique) + "</td>" +
        '<td class="num-cell"' + missStyle + ">" + fmtNum(f.missing_pct, 1) + "%</td>" +
        '<td style="text-align:right;"><span class="sel wide" style="justify-content:space-between"><span class="zh">' + esc(m.zh) +
        '</span><span class="en">' + esc(m.en) + '</span><span class="car"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M6 9l6 6 6-6"></path></svg></span></span></td>' +
        "</tr>";
    }).join("");

    sm.fields.forEach(function (f, i) {
      var row = tbody.rows[i];
      var chip = row && row.querySelector(".sel");
      if (!chip) return;
      var sel = chipEmbedSelect(chip, ROLE_OPTIONS, function (v) {
        api("/api/" + cache.sessionId + "/semantics", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ column: f.column, role: v }),
        }).then(function (res) {
          cache.semantics = res;
          renderRoles();
          refreshOverview(); // roles feed the overview: recompute metrics/findings
        }).catch(showLoadError);
      });
      sel.value = f.role;
    });
  }

  var FINDING_ICONS = {
    warn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"></path></svg>',
    info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 16v-4M12 8h.01"></path><circle cx="12" cy="12" r="9"></circle></svg>',
    good: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 17l6-6 4 4 8-8"></path><path d="M21 7v5h-5" opacity=".6"></path></svg>',
  };

  function findingClass(zh) {
    if (/重复|异常|超过 10%|缺失率超过/.test(zh)) return "warn";
    if (/相关|差异/.test(zh)) return "good";
    return "info";
  }

  function renderFindings() {
    var ov = cache.overview;
    if (!ov) return;
    var wrap = $("#ins-findings");
    var zh = (ov.findings && ov.findings.zh) || [];
    var en = (ov.findings && ov.findings.en) || [];
    var count = $("#ins-findings-count");
    if (count) count.textContent = String(zh.length);
    if (!wrap) return;
    wrap.innerHTML = zh.map(function (z, i) {
      var cls = findingClass(z);
      return '<div class="ins ' + cls + '"><span class="ib">' + FINDING_ICONS[cls] + "</span>" +
        dual(richText(z), richText(en[i] !== undefined ? en[i] : z)) + "</div>";
    }).join("") || '<div class="ins info"><span class="ib">' + FINDING_ICONS.info + "</span>" +
      dual("暂无可报告的发现。", "Nothing to report yet.") + "</div>";
  }

  function renderSuggestions() {
    var ov = cache.overview;
    if (!ov) return;
    var wrap = $("#ins-suggestions");
    var zh = (ov.suggestions && ov.suggestions.zh) || [];
    var en = (ov.suggestions && ov.suggestions.en) || [];
    var count = $("#ins-suggestions-count");
    if (count) count.textContent = String(zh.length);
    if (!wrap) return;
    wrap.innerHTML = zh.map(function (z, i) {
      return '<div class="ins info"><span class="ib" style="background:var(--accent-soft);color:var(--accent);font-weight:700;font-size:12px;">' + (i + 1) + "</span>" +
        dual(richText(z), richText(en[i] !== undefined ? en[i] : z)) + "</div>";
    }).join("") || '<div class="ins info"><span class="ib">' + FINDING_ICONS.info + "</span>" +
      dual("暂无建议。", "No suggestions yet.") + "</div>";
  }

  function renderAll() {
    renderMode();
    renderMetrics();
    renderRoles();
    renderFindings();
    renderSuggestions();
  }

  /* ---------- loading ---------- */

  function refreshOverview() {
    return api("/api/" + cache.sessionId + "/general-overview").then(function (ov) {
      cache.overview = ov;
      renderMetrics();
      renderFindings();
      renderSuggestions();
    }).catch(showLoadError);
  }

  function ensureLoaded() {
    var sid = sessionId();
    if (!sid) {
      showHint("请先在「上传」步骤导入数据。", "Upload a dataset in the Upload step first.");
      return;
    }
    if (cache.loading) return;
    if (cache.sessionId === sid && cache.overview) return;

    cache.loading = true;
    showHint("正在分析…", "Analyzing…");
    Promise.all([
      api("/api/" + sid + "/mode"),
      api("/api/" + sid + "/semantics"),
      api("/api/" + sid + "/general-overview"),
    ]).then(function (res) {
      cache.sessionId = sid;
      cache.mode = res[0];
      cache.semantics = res[1];
      cache.overview = res[2];
      cache.loading = false;
      renderAll();
    }).catch(function (err) {
      cache.loading = false;
      cache.overview = null;
      showLoadError(err);
    });
  }

  /* ---------- boot ---------- */

  function boot() {
    var step = $('.step[data-screen="insight"]');
    if (step) step.addEventListener("click", ensureLoaded);
    document.addEventListener("click", function (e) {
      if (e.target.closest('[data-go="insight"]')) ensureLoaded();
    });

    var reset = $("#ins-role-reset");
    if (reset) {
      reset.addEventListener("click", function () {
        if (!cache.sessionId) return;
        api("/api/" + cache.sessionId + "/semantics", { method: "DELETE" }).then(function (res) {
          cache.semantics = res;
          renderRoles();
          refreshOverview();
        }).catch(showLoadError);
      });
    }

    /* page reloaded while this screen was active (nav.js restores it) */
    var screen = $("#screen-insight");
    if (screen && screen.classList.contains("active")) ensureLoaded();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
