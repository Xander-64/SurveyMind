/* SurveyMind · data layer
 *
 * Replaces the design mockup's placeholder data with live results from the
 * FastAPI backend. Constraints honoured throughout:
 *   - static DOM / classNames / CSS / SVG icons stay untouched;
 *   - dynamic rows & cells are rebuilt with the exact same classes and
 *     inline-style patterns the mockup already uses;
 *   - the only new interactive controls are the two cross-tab selects,
 *     embedded invisibly inside the mockup's own .sel chips.
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

  var state = {
    sessionId: null,
    filename: "",
    overview: null,
    detect: null,
    stats: null,
    crossGroup: "",
    crossTarget: "",
    previewRows: 6,
    previewCol: "",
  };

  /* ---------- helpers ---------- */

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function lang() { return document.body.getAttribute("data-lang") === "en" ? "en" : "zh"; }
  function apiLang() { return lang() === "en" ? "en" : "zh-CN"; }

  function api(path, opts) {
    return fetch(API + path, opts).then(function (r) {
      if (!r.ok) { return r.json().catch(function () { return {}; }).then(function (b) { throw new Error(b.detail || ("HTTP " + r.status)); }); }
      return r.json();
    });
  }

  function fmtInt(n) { return Number(n).toLocaleString("en-US"); }
  function fmtNum(n, d) {
    if (n === null || n === undefined || isNaN(n)) return "—";
    return Number(n).toFixed(d === undefined ? 1 : d).replace(/\.0+$/, "");
  }
  function setText(el, text) { if (el) el.textContent = text; }
  function setBoth(el, zhText, enText) {
    if (!el) return;
    var zh = el.querySelector(".zh"), en = el.querySelector(".en");
    if (zh) zh.textContent = zhText;
    if (en) en.textContent = enText !== undefined ? enText : zhText;
    if (!zh && !en) el.textContent = zhText;
  }

  /* mockup bar chart: <div class="bars"><div class="b" style="height:x%"> */
  function renderBars(container, values, highlightMax) {
    if (!container) return;
    var max = Math.max.apply(null, values.concat([1]));
    container.innerHTML = "";
    values.forEach(function (v) {
      var b = document.createElement("div");
      b.className = "b" + (highlightMax && v === max ? " hl" : "");
      b.style.height = Math.max(3, Math.round((v / max) * 100)) + "%";
      container.appendChild(b);
    });
  }

  function renderAxis(container, labels) {
    if (!container) return;
    container.innerHTML = "";
    labels.forEach(function (t) {
      var s = document.createElement("span");
      s.textContent = t;
      container.appendChild(s);
    });
  }

  /* accent-blue interpolation for heatmap cells (mockup palette endpoints) */
  function heatColor(ratio) {
    var lo = [236, 241, 249], hi = [62, 92, 153];
    var c = lo.map(function (l, i) { return Math.round(l + (hi[i] - l) * ratio); });
    return "rgb(" + c.join(",") + ")";
  }

  var TYPE_ZH = { num: "数值", scale: "量表", single: "单选", multi: "多选", open: "开放", empty: "空列" };
  var TYPE_EN = { num: "Numeric", scale: "Scale", single: "Single", multi: "Multi", open: "Open", empty: "Empty" };

  function typeBadge(short) {
    return '<span class="tb ' + short + '"><span class="d"></span><span class="zh">' + (TYPE_ZH[short] || short) +
      '</span><span class="en">' + (TYPE_EN[short] || short) + "</span></span>";
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* ---------- chrome (topnav + sidebar) ---------- */

  function renderChrome() {
    var fileChip = $(".topnav .file");
    if (fileChip) {
      fileChip.innerHTML = '<span class="dot"></span>' + esc(state.filename);
    }
    setText($(".side-foot .fn"), state.filename);
    var meta = $(".side-foot .meta");
    if (meta && state.overview) {
      setBoth(meta, fmtInt(state.overview.rows) + " 行 · " + state.overview.columns + " 字段",
        fmtInt(state.overview.rows) + " rows · " + state.overview.columns + " fields");
    }
    var isDemo = state.filename === "sample_survey.csv";
    $all(".side-foot .sample").forEach(function (s) {
      if (s.classList.contains("zh")) s.textContent = isDemo ? "示例数据 · 可替换" : "本地上传 · 本会话有效";
      else s.textContent = isDemo ? "Sample data · replaceable" : "Local upload · this session";
    });
  }

  /* ---------- overview screen ---------- */

  function renderOverview() {
    var ov = state.overview, dt = state.detect;
    if (!ov) return;
    var screen = $("#screen-overview");

    setBoth($(".lede.zh", screen) ? { querySelector: function () { return null; } } : null, "", "");
    var ledes = $all(".page-head .lede", screen);
    ledes.forEach(function (p) {
      if (p.classList.contains("zh")) p.textContent = "已成功解析 " + state.filename + " — 关键指标、自动洞察与逐字段缺失分布一览。";
      else p.textContent = "Parsed " + state.filename + " — key metrics, auto insights and per-field missingness at a glance.";
    });

    var metrics = $all(".metrics .metric", screen);
    /* metric 1: rows */
    if (metrics[0]) {
      setText($(".v", metrics[0]), fmtInt(ov.rows));
      var foot0 = $(".foot", metrics[0]);
      if (foot0) foot0.innerHTML = '<span class="zh">来自 ' + esc(state.filename) + '</span><span class="en">from ' + esc(state.filename) + "</span>";
    }
    /* metric 2: fields */
    if (metrics[1]) {
      setText($(".v", metrics[1]), ov.columns);
      var counts = (dt && dt.counts) || {};
      var covar = ov.columns - ov.question_count;
      setBoth($(".foot", metrics[1]), ov.question_count + " 题 · " + covar + " 空列", ov.question_count + " questions · " + covar + " empty");
    }
    /* metric 3: missing */
    if (metrics[2]) {
      var pct = (ov.missing_ratio * 100);
      var v2 = $(".v", metrics[2]);
      if (v2) v2.innerHTML = fmtNum(pct, 1) + "<small>%</small>";
      var donut = $(".donut", metrics[2]);
      if (donut) {
        var deg = Math.max(0, Math.min(360, pct * 3.6));
        donut.style.background = "conic-gradient(var(--accent) 0 " + deg.toFixed(1) + "deg,#E6EBF3 " + deg.toFixed(1) + "deg 360deg)";
        setText($(".lab", donut), fmtNum(pct, 1) + "%");
      }
      var missingCols = ov.column_meta.filter(function (c) { return c.missing_ratio > 0; }).length;
      setBoth($(".foot", metrics[2]), "分布于 " + missingCols + " 个字段", "in " + missingCols + " fields");
    }
    /* metric 4: questions + type breakdown */
    if (metrics[3]) {
      setText($(".v", metrics[3]), ov.question_count);
      var c = (dt && dt.counts) || {};
      var partsZh = [], partsEn = [];
      [["scale", "量表"], ["single", "单选"], ["multi", "多选"], ["open", "开放"], ["num", "数值"]].forEach(function (p) {
        if (c[p[0]]) { partsZh.push(p[1] + c[p[0]]); partsEn.push(c[p[0]] + " " + p[0]); }
      });
      setBoth($(".foot", metrics[3]), partsZh.join(" · ") || "—", partsEn.join(" · ") || "—");
    }

    renderInsights(screen);
    renderMissingChart(screen);
    renderPreviewTable(screen);
  }

  function renderInsights(screen) {
    var ov = state.overview, dt = state.detect, st = state.stats;
    var card = $all(".card", screen)[0];
    if (!card) return;
    var wrap = card.querySelector(".card-h").nextElementSibling;
    if (!wrap) return;

    var insights = [];
    var worst = ov.column_meta.slice().sort(function (a, b) { return b.missing_ratio - a.missing_ratio; })[0];
    if (worst && worst.missing_ratio > 0.05) {
      insights.push({
        cls: "warn",
        icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"></path></svg>',
        zh: "<b>「" + esc(worst.column_name) + "」字段缺失 " + fmtNum(worst.missing_ratio * 100, 1) + "%</b> — 建议在描述统计前处理，或保留为「未填」类别。",
        en: '<b>"' + esc(worst.column_name) + '" is ' + fmtNum(worst.missing_ratio * 100, 1) + '% missing</b> — handle before stats, or keep as an "unfilled" category.',
      });
    }
    var openCols = dt ? dt.types.filter(function (t) { return t.short === "open"; }) : [];
    if (openCols.length) {
      insights.push({
        cls: "info",
        icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 16v-4M12 8h.01"></path><circle cx="12" cy="12" r="9"></circle></svg>',
        zh: "<b>「" + esc(openCols[0].column) + "」识别为开放题</b> — 统计阶段将展示原始回答与高频回答，而非均值。",
        en: '<b>"' + esc(openCols[0].column) + '" is open-ended</b> — raw answers and frequent responses will be shown instead of a mean.',
      });
    }
    if (st && st.scale_summary && st.scale_summary.length) {
      var top = st.scale_summary.slice().sort(function (a, b) { return b.mean - a.mean; })[0];
      insights.push({
        cls: "good",
        icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 17l6-6 4 4 8-8"></path><path d="M21 7v5h-5" opacity=".6"></path></svg>',
        zh: "<b>「" + esc(top.column) + "」在量表题中均值最高</b>（" + fmtNum(top.mean, 2) + "）— 可在交叉分析中按人群进一步比较。",
        en: "<b>\"" + esc(top.column) + "\" has the highest scale mean</b> (" + fmtNum(top.mean, 2) + ") — compare across groups in cross-tab.",
      });
    }

    setText(card.querySelector(".card-h .sub"), String(insights.length));
    wrap.innerHTML = insights.map(function (i) {
      return '<div class="ins ' + i.cls + '"><span class="ib">' + i.icon + "</span>" +
        '<span class="zh">' + i.zh + "</span>" + '<span class="en">' + i.en + "</span></div>";
    }).join("");
  }

  function renderMissingChart(screen) {
    var ov = state.overview;
    var card = $all(".card", screen)[1];
    if (!card) return;
    var cols = ov.column_meta.slice().sort(function (a, b) { return b.missing_ratio - a.missing_ratio; }).slice(0, 8);
    var values = cols.map(function (c) { return c.missing_ratio; });
    var max = Math.max.apply(null, values.concat([0.0001]));
    var bars = card.querySelector(".bars");
    if (bars) {
      bars.innerHTML = "";
      cols.forEach(function (c, i) {
        var b = document.createElement("div");
        b.className = "b" + (i < 2 && c.missing_ratio > 0 ? " hl" : "");
        b.style.height = Math.max(3, Math.round((c.missing_ratio / max) * 100)) + "%";
        bars.appendChild(b);
      });
    }
    renderAxis(card.querySelector(".axis"), cols.map(function (c) {
      var n = String(c.column_name);
      return n.length > 4 ? n.slice(0, 4) : n;
    }));
  }

  function renderPreviewTable(screen) {
    var ov = state.overview;
    var table = screen.querySelector("table.dt");
    if (!table || !ov.preview.length) return;
    var cols = Object.keys(ov.preview[0]);
    if (state.previewCol && cols.indexOf(state.previewCol) >= 0) cols = [state.previewCol];
    table.querySelector("thead tr").innerHTML = cols.map(function (c) { return "<th>" + esc(c) + "</th>"; }).join("");
    table.querySelector("tbody").innerHTML = ov.preview.slice(0, state.previewRows || 6).map(function (row) {
      return "<tr>" + cols.map(function (c) {
        var v = row[c];
        if (v === null || v === undefined) return '<td><span class="null">— null</span></td>';
        if (typeof v === "number") return '<td class="num-cell">' + esc(fmtNum(v, 2)) + "</td>";
        return "<td>" + esc(v) + "</td>";
      }).join("") + "</tr>";
    }).join("");
  }

  /* value spans of a .sel chip = its direct .zh/.en children minus the .lab ones */
  function chipSetValue(chip, zhText, enText) {
    var kids = Array.prototype.slice.call(chip.children);
    kids.forEach(function (k) {
      if (k.classList.contains("lab") || k.classList.contains("car")) return;
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

  function bindPreviewControls() {
    var screen = $("#screen-overview");
    var chips = $all(".card-h .sel", screen);
    if (chips.length < 2 || !state.overview || !state.overview.preview.length) return;

    var maxRows = Math.min(10, state.overview.preview.length);
    var rowOpts = [{ value: "6", label: "前 6 行 / First 6" }];
    if (maxRows > 6) rowOpts.push({ value: String(maxRows), label: "前 " + maxRows + " 行 / First " + maxRows });
    var s1 = chipEmbedSelect(chips[0], rowOpts, function (v) {
      state.previewRows = parseInt(v, 10) || 6;
      chipSetValue(chips[0], "前 " + v + " 行", "First " + v);
      renderPreviewTable(screen);
    });
    s1.value = String(state.previewRows || 6);

    var cols = Object.keys(state.overview.preview[0]);
    var colOpts = [{ value: "", label: "全部列 / All columns" }].concat(
      cols.map(function (c) { return { value: c, label: c }; })
    );
    var s2 = chipEmbedSelect(chips[1], colOpts, function (v) {
      state.previewCol = v;
      chipSetValue(chips[1], v || "列显示", v || "Columns");
      renderPreviewTable(screen);
    });
    s2.value = state.previewCol || "";

    /* keep chip labels in sync with state (e.g. after a new upload reset) */
    chipSetValue(chips[0], "前 " + (state.previewRows || 6) + " 行", "First " + (state.previewRows || 6));
    chipSetValue(chips[1], state.previewCol || "列显示", state.previewCol || "Columns");
  }

  /* ---------- types screen ---------- */

  function renderTypes() {
    var dt = state.detect, ov = state.overview;
    if (!dt) return;
    var screen = $("#screen-types");
    var counts = dt.counts || {};

    ["num", "scale", "single", "multi", "open"].forEach(function (key) {
      var chip = screen.querySelector(".legend .tb." + key);
      if (!chip) return;
      var zh = chip.querySelector(".zh"), en = chip.querySelector(".en");
      if (zh) zh.textContent = TYPE_ZH[key] + " " + TYPE_EN[key];
      if (en) en.textContent = TYPE_EN[key];
      /* trailing " · N" lives as a text node after the spans */
      while (chip.lastChild && chip.lastChild.nodeType === 3) chip.removeChild(chip.lastChild);
      chip.appendChild(document.createTextNode(" · " + (counts[key] || 0)));
    });
    var legendNote = screen.querySelector(".legend > span:last-child");
    if (legendNote) {
      setBoth(legendNote, dt.types.length + " 个字段", dt.types.length + " fields");
    }

    var meta = {};
    (ov ? ov.column_meta : []).forEach(function (c) { meta[c.column_name] = c; });
    var samples = {};
    (ov ? ov.preview : []).slice(0, 5).forEach(function (row) {
      Object.keys(row).forEach(function (c) {
        if (row[c] === null || row[c] === undefined) return;
        (samples[c] = samples[c] || []).push(String(row[c]));
      });
    });

    var tbody = screen.querySelector("table.dt tbody");
    if (!tbody) return;
    tbody.innerHTML = dt.types.map(function (t) {
      var m = meta[t.column] || {};
      var sample = (samples[t.column] || []).slice(0, 4).join(", ");
      if (sample.length > 26) sample = sample.slice(0, 26) + "…";
      var missPct = (m.missing_ratio || 0) * 100;
      var missStyle = missPct > 2 ? ' style="color:var(--warn);font-weight:600"' : "";
      var selLabel = TYPE_ZH[t.short] + " " + TYPE_EN[t.short];
      return "<tr>" +
        '<td><b style="color:var(--ink)">' + esc(t.column) + "</b></td>" +
        '<td class="mono" style="font-size:11.5px;color:var(--ink-3)">' + esc(sample || "—") + "</td>" +
        '<td class="num-cell">' + (m.unique_values !== undefined ? m.unique_values : "—") + "</td>" +
        '<td class="num-cell"' + missStyle + ">" + fmtNum(missPct, 1) + "%</td>" +
        "<td>" + typeBadge(t.short) + "</td>" +
        '<td><span class="mono" style="font-size:11px;color:var(--muted)">—</span></td>' +
        '<td style="text-align:right;"><span class="sel wide" style="justify-content:space-between"><span class="zh">' + esc(selLabel) +
        '</span><span class="en">' + esc(TYPE_EN[t.short]) + '</span><span class="car"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M6 9l6 6 6-6"></path></svg></span></span></td>' +
        "</tr>";
    }).join("");

    /* wire the override dropdowns — change persists via POST /types, then the
       whole app reloads so stats/cross/report follow the corrected type */
    var typeOptions = [
      { value: "num", label: "数值 Numeric" },
      { value: "scale", label: "量表 Scale" },
      { value: "single", label: "单选 Single" },
      { value: "multi", label: "多选 Multi" },
      { value: "open", label: "开放 Open" },
    ];
    dt.types.forEach(function (t, i) {
      if (t.short === "empty") return;
      var row = tbody.rows[i];
      var chip = row && row.querySelector(".sel");
      if (!chip) return;
      var selEl = chipEmbedSelect(chip, typeOptions, function (v) {
        api("/api/" + state.sessionId + "/types", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ column: t.column, type: v }),
        }).then(loadAll).catch(showError);
      });
      selEl.value = t.short;
    });

    var resetBtn = screen.querySelector(".head-actions .btn.ghost");
    if (resetBtn && !resetBtn.dataset.smBound) {
      resetBtn.dataset.smBound = "1";
      resetBtn.addEventListener("click", function () {
        if (!state.sessionId) return;
        api("/api/" + state.sessionId + "/types", { method: "DELETE" }).then(loadAll).catch(showError);
      });
    }
  }

  /* ---------- stats screen ---------- */

  function statTemplates(grid) {
    if (statTemplates.cache) return statTemplates.cache;
    var cards = $all(".stat-card", grid);
    var byType = {};
    cards.forEach(function (c) {
      var tb = c.querySelector(".tb");
      ["num", "scale", "single", "multi", "open"].forEach(function (k) {
        if (tb && tb.classList.contains(k) && !byType[k]) byType[k] = c.cloneNode(true);
      });
    });
    /* the horizontal-bars "gender" card is the first .single one; keep the
       vertical-bars variant (region) as the general single template */
    var singles = cards.filter(function (c) { var tb = c.querySelector(".tb"); return tb && tb.classList.contains("single"); });
    if (singles[1]) byType.single = singles[1].cloneNode(true);
    statTemplates.cache = byType;
    return byType;
  }

  function kpiHTML(pairs) {
    return pairs.map(function (p) {
      return '<div class="kpi" style="font-size:10.5px;color:var(--muted)"><span class="zh">' + p[0] + '</span><span class="en">' + p[1] +
        '</span><b style="display:block;font-size:18px;font-weight:700;color:var(--ink)">' + p[2] + "</b></div>";
    }).join("");
  }

  function fillCardHead(card, name, short) {
    var top = card.querySelector(".stat-top");
    top.innerHTML = '<div><div class="nm" style="font-size:14.5px;font-weight:700">' + esc(name) +
      '</div><div class="fld mono" style="font-size:10.5px;color:var(--faint)">' + esc(name) + "</div></div>" + typeBadge(short);
  }

  function renderStats() {
    var st = state.stats, dt = state.detect;
    if (!st || !dt) return;
    var screen = $("#screen-stats");
    var grid = screen.querySelector('div[style*="grid-template-columns"]');
    if (!grid) return;
    var tpl = statTemplates(grid);
    var helper = $all(".card", grid).filter(function (c) { return !c.classList.contains("stat-card"); })[0];

    var numericSummary = {};
    (st.numeric_summary || []).forEach(function (r) { numericSummary[r.column] = r; });
    var scaleSummary = {};
    (st.scale_summary || []).forEach(function (r) { scaleSummary[r.column] = r; });

    grid.innerHTML = "";
    dt.types.forEach(function (t) {
      var short = t.short, col = t.column;
      if (short === "empty" || !tpl[short]) return;
      var card = tpl[short].cloneNode(true);
      fillCardHead(card, col, short);
      var kpis = card.querySelector(".kpis");
      var bars = card.querySelector(".bars");
      var axis = card.querySelector(".axis");

      if (short === "num") {
        var s = numericSummary[col] || {};
        var h = (st.numeric_histograms || {})[col];
        kpis.innerHTML = kpiHTML([["均值", "Mean", fmtNum(s.mean)], ["中位", "Median", fmtNum(s.median)], ["SD", "SD", fmtNum(s.std)], ["范围", "Range", fmtNum(s.min, 0) + "–" + fmtNum(s.max, 0)]]);
        if (h) { renderBars(bars, h.counts, true); renderAxis(axis, [fmtNum(h.min, 0), "直方图", fmtNum(h.max, 0)]); }
        else if (bars) { renderBars(bars, [1], false); renderAxis(axis, ["—"]); }
      } else if (short === "scale") {
        var sc = scaleSummary[col] || {};
        var dist = (st.scale_distributions || {})[col] || [];
        kpis.innerHTML = kpiHTML([["均值", "Mean", fmtNum(sc.mean)], ["中位", "Median", fmtNum(sc.median)], ["SD", "SD", fmtNum(sc.std)], ["n", "n", fmtNum(sc.count, 0)]]);
        renderBars(bars, dist.map(function (d) { return d.count; }), true);
        renderAxis(axis, dist.length ? [String(dist[0].score), "分布", String(dist[dist.length - 1].score)] : ["—"]);
      } else if (short === "single" || short === "multi") {
        var freq = ((st.frequency_tables || {})[col] || []).slice(0, 7);
        var total = freq.reduce(function (a, r) { return a + r.count; }, 0);
        if (short === "single") {
          kpis.innerHTML = kpiHTML([["众数", "Mode", esc(String(freq.length ? freq[0].response : "—")).slice(0, 6)], ["占比", "Share", freq.length ? fmtNum(freq[0].percentage, 0) + "%" : "—"], ["类别", "Levels", String(((st.frequency_tables || {})[col] || []).length)]]);
        } else {
          kpis.innerHTML = kpiHTML([["选项", "Options", String(((st.frequency_tables || {})[col] || []).length)], ["总选择", "Picks", fmtInt(total)], ["最高", "Top", esc(String(freq.length ? freq[0].response : "—")).slice(0, 6)]]);
        }
        renderBars(bars, freq.map(function (r) { return r.count; }), true);
        renderAxis(axis, freq.slice(0, 5).map(function (r) { var s2 = String(r.response); return s2.length > 4 ? s2.slice(0, 4) : s2; }));
      } else if (short === "open") {
        var ot = (st.open_text || {})[col] || { total: 0, answers: [] };
        var avgLen = ot.answers.length ? Math.round(ot.answers.reduce(function (a, x) { return a + x.length; }, 0) / ot.answers.length) : 0;
        var freqMap = {};
        ot.answers.forEach(function (a) { var k = a.trim(); freqMap[k] = (freqMap[k] || 0) + 1; });
        var tops = Object.keys(freqMap).map(function (k) { return [k, freqMap[k]]; })
          .sort(function (a, b) { return b[1] - a[1]; }).slice(0, 8);
        kpis.innerHTML = kpiHTML([["有效回答", "Responses", fmtInt(ot.total)], ["平均字数", "Avg length", String(avgLen)], ["高频回答", "Top answers", String(tops.length)]]);
        var pillWrap = card.querySelector(".kpis").nextElementSibling;
        if (pillWrap) {
          pillWrap.innerHTML = tops.map(function (p, i) {
            var size = i === 0 ? 14 : i === 1 ? 13 : i < 4 ? 12 : 11;
            var label = p[0].length > 12 ? p[0].slice(0, 12) + "…" : p[0];
            return '<span class="pill" style="font-size:' + size + 'px"><b>' + esc(label) + '</b><span class="mono" style="font-size:10.5px;color:var(--faint)">' + p[1] + "</span></span>";
          }).join("");
        }
      }
      grid.appendChild(card);
    });
    if (helper) grid.appendChild(helper);
  }

  /* ---------- cross screen ---------- */

  function embedSelect(chip, options, onChange) {
    /* keeps the mockup .sel chip visuals; a transparent native <select> sits
       on top so the design tokens render while the control is real */
    var old = chip.querySelector("select");
    if (old) old.remove();
    var sel = document.createElement("select");
    sel.style.cssText = "position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:pointer;";
    options.forEach(function (o) {
      var opt = document.createElement("option");
      opt.value = o; opt.textContent = o;
      sel.appendChild(opt);
    });
    chip.style.position = "relative";
    sel.addEventListener("change", function () {
      var label = chip.querySelector("span");
      if (label) label.textContent = sel.value;
      onChange(sel.value);
    });
    chip.appendChild(sel);
    return sel;
  }

  function renderCrossControls() {
    var dt = state.detect;
    if (!dt) return;
    var screen = $("#screen-cross");
    var chips = $all(".sel.wide", screen);
    if (chips.length < 2) return;
    var catCols = dt.types.filter(function (t) { return t.short === "single" || t.short === "multi" || t.short === "scale"; })
      .map(function (t) { return t.column; });
    if (!catCols.length) return;

    state.crossGroup = state.crossGroup || catCols[0];
    state.crossTarget = state.crossTarget || catCols[1] || catCols[0];

    var g = embedSelect(chips[0], catCols, function (v) { state.crossGroup = v; });
    g.value = state.crossGroup;
    setText(chips[0].querySelector("span"), state.crossGroup);
    var t = embedSelect(chips[1], catCols, function (v) { state.crossTarget = v; });
    t.value = state.crossTarget;
    setText(chips[1].querySelector("span"), state.crossTarget);

    var run = screen.querySelector(".btn.primary:not([data-go])");
    if (run && !run.dataset.smBound) {
      run.dataset.smBound = "1";
      run.addEventListener("click", runCross);
    }
  }

  function runCross() {
    var screen = $("#screen-cross");
    api("/api/" + state.sessionId + "/cross", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ group_col: state.crossGroup, target_col: state.crossTarget, language: apiLang() }),
    }).then(function (res) {
      var title = screen.querySelector(".card:nth-of-type(2) .card-h h3") || screen.querySelectorAll(".card")[1].querySelector("h3");
      setBoth(title, state.crossGroup + " × " + state.crossTarget, state.crossGroup + " × " + state.crossTarget);
      var hm = screen.querySelector(".hm");
      var sig = screen.querySelector(".sig");

      if (res.analysis_type === "categorical_crosstab") {
        var cols = res.cols, rows = res.rows;
        hm.style.gridTemplateColumns = "88px repeat(" + cols.length + ",1fr)";
        var html = '<div class="cl"></div>' + cols.map(function (c) { return '<div class="cl">' + esc(String(c).slice(0, 8)) + "</div>"; }).join("");
        rows.forEach(function (r, i) {
          html += '<div class="rl">' + esc(String(r).slice(0, 8)) + "</div>";
          res.row_pct[i].forEach(function (p) {
            var ratio = Math.max(0, Math.min(1, p / 60));
            var fg = ratio > 0.35 ? "#fff" : "#8b97b2";
            html += '<div class="hc" style="background:' + heatColor(ratio) + ";color:" + fg + '">' + Math.round(p) + "%</div>";
          });
        });
        hm.innerHTML = html;
        if (sig) {
          sig.innerHTML = '<span class="tag ok">n = ' + fmtInt(res.counts.reduce(function (a, row) { return a + row.reduce(function (x, y) { return x + y; }, 0); }, 0)) + "</span>" +
            '<span class="mono">' + rows.length + " × " + cols.length + "</span>" +
            '<span class="zh">' + esc(res.interpretation) + "</span>" + '<span class="en">' + esc(res.interpretation) + "</span>";
        }
      } else if (res.analysis_type === "numeric_by_group") {
        var table = res.summary_table;
        hm.style.gridTemplateColumns = "88px repeat(4,1fr)";
        var head = ["n", "mean", "median", "SD"];
        var html2 = '<div class="cl"></div>' + head.map(function (h) { return '<div class="cl">' + h + "</div>"; }).join("");
        var means = table.map(function (r) { return r.mean; });
        var maxMean = Math.max.apply(null, means), minMean = Math.min.apply(null, means);
        table.forEach(function (r) {
          html2 += '<div class="rl">' + esc(String(r.group).slice(0, 8)) + "</div>";
          var ratio = maxMean === minMean ? 0.5 : (r.mean - minMean) / (maxMean - minMean);
          html2 += '<div class="hc" style="background:var(--surface-3);color:var(--ink-2)">' + fmtNum(r.count, 0) + "</div>";
          html2 += '<div class="hc" style="background:' + heatColor(ratio) + ";color:" + (ratio > 0.35 ? "#fff" : "#8b97b2") + '">' + fmtNum(r.mean, 2) + "</div>";
          html2 += '<div class="hc" style="background:var(--surface-3);color:var(--ink-2)">' + fmtNum(r.median, 2) + "</div>";
          html2 += '<div class="hc" style="background:var(--surface-3);color:var(--ink-2)">' + fmtNum(r.std, 2) + "</div>";
        });
        hm.innerHTML = html2;
        if (sig) {
          sig.innerHTML = '<span class="tag ok">' + esc(state.crossTarget) + "</span>" +
            '<span class="mono">by ' + esc(state.crossGroup) + "</span>" +
            '<span class="zh">' + esc(res.interpretation) + "</span>" + '<span class="en">' + esc(res.interpretation) + "</span>";
        }
      } else if (sig) {
        sig.innerHTML = '<span class="tag">—</span><span class="zh">' + esc(res.message || "该组合暂不支持") + "</span>" +
          '<span class="en">' + esc(res.message || "Combination not supported") + "</span>";
      }
    }).catch(showError);
  }

  /* ---------- export screen ---------- */

  function mdToHTML(md) {
    var out = [];
    md.split("\n").forEach(function (line) {
      if (/^# /.test(line)) out.push("<h2>" + esc(line.slice(2)) + "</h2>");
      else if (/^## /.test(line)) out.push("<h3>" + esc(line.slice(3)) + "</h3>");
      else if (/^- /.test(line)) out.push('<p style="margin:2px 0">· ' + esc(line.slice(2)).replace(/`([^`]+)`/g, "<b>$1</b>") + "</p>");
      else if (/^\d+\. /.test(line)) out.push('<p style="margin:2px 0">' + esc(line).replace(/`([^`]+)`/g, "<b>$1</b>") + "</p>");
      else if (line.trim()) out.push("<p>" + esc(line).replace(/`([^`]+)`/g, "<b>$1</b>") + "</p>");
    });
    return out.join("");
  }

  function renderExport() {
    var screen = $("#screen-export");
    var doc = screen.querySelector(".doc");
    var fnBadge = screen.querySelector(".card-h .sub.mono");
    if (fnBadge) fnBadge.textContent = state.filename.replace(/\.[^.]+$/, "") + "_report.md";
    if (!doc || !state.sessionId) return;

    api("/api/" + state.sessionId + "/report?language=" + encodeURIComponent(apiLang()))
      .then(function (res) { doc.innerHTML = mdToHTML(res.markdown); })
      .catch(function () { /* leave mockup preview on failure */ });

    var exportBtn = screen.querySelector(".head-actions .btn.primary");
    if (exportBtn && !exportBtn.dataset.smBound) {
      exportBtn.dataset.smBound = "1";
      exportBtn.addEventListener("click", function () {
        window.open(API + "/api/" + state.sessionId + "/report?language=" + encodeURIComponent(apiLang()) + "&download=true", "_blank");
      });
    }
    var copyBtn = screen.querySelector(".head-actions .btn.ghost");
    if (copyBtn && !copyBtn.dataset.smBound) {
      copyBtn.dataset.smBound = "1";
      copyBtn.addEventListener("click", function () {
        api("/api/" + state.sessionId + "/report?language=" + encodeURIComponent(apiLang())).then(function (res) {
          navigator.clipboard.writeText(res.markdown);
        });
      });
    }

    /* AI interpretation — POST /ai-report; degrades gracefully without a key */
    var aiBtn = $("#ai-report-btn");
    var aiCard = $("#ai-report-card");
    var aiDoc = $("#ai-report-doc");
    var aiStatus = $("#ai-report-status");
    if (aiBtn && aiCard && aiDoc && !aiBtn.dataset.smBound) {
      aiBtn.dataset.smBound = "1";
      aiBtn.addEventListener("click", function () {
        if (!state.sessionId || aiBtn.disabled) return;
        var zh = aiBtn.querySelector(".zh"), en = aiBtn.querySelector(".en");
        var oldZh = zh.textContent, oldEn = en.textContent;
        aiBtn.disabled = true;
        aiBtn.style.opacity = ".6";
        zh.textContent = "生成中…";
        en.textContent = "Generating…";
        if (aiStatus) aiStatus.textContent = "";

        api("/api/" + state.sessionId + "/ai-report", { method: "POST" }).then(function (res) {
          aiCard.style.display = "";
          if (res.ok) {
            aiDoc.innerHTML = mdToHTML(res.markdown);
          } else if (res.reason === "not_configured") {
            aiDoc.innerHTML =
              '<p class="zh">需配置 API key：将项目根目录的 <b>.env.example</b> 复制为 <b>.env</b>，' +
              "填入你的 <b>LLM_API_KEY</b>，然后重启后端。</p>" +
              '<p class="en">API key required: copy <b>.env.example</b> to <b>.env</b>, ' +
              "fill in <b>LLM_API_KEY</b>, then restart the backend.</p>";
          } else {
            aiDoc.innerHTML =
              '<p class="zh">AI 调用失败：' + esc(res.message || "未知错误") + "</p>" +
              '<p class="en">AI request failed: ' + esc(res.message || "unknown error") + "</p>";
          }
          aiCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }).catch(function (err) {
          aiCard.style.display = "";
          aiDoc.innerHTML = "<p>" + esc(err && err.message ? err.message : "请求失败 / request failed") + "</p>";
        }).then(function () {
          aiBtn.disabled = false;
          aiBtn.style.opacity = "";
          zh.textContent = oldZh;
          en.textContent = oldEn;
        });
      });
    }
  }

  /* ---------- upload ---------- */

  /* mirror of nav.js's private setScreen — same classes, same behaviour */
  function smShowScreen(name) {
    var target = document.getElementById("screen-" + name);
    if (!target) return;
    var order = ["upload", "overview", "types", "stats", "cross", "export"];
    $all(".screen").forEach(function (s) { s.classList.toggle("active", s === target); });
    var idx = order.indexOf(name);
    $all(".step").forEach(function (st) {
      var n = st.getAttribute("data-screen");
      var i = order.indexOf(n);
      st.classList.toggle("current", n === name);
      st.classList.toggle("done", i > -1 && i < idx);
    });
    var main = document.getElementById("main");
    if (main) main.scrollTop = 0;
    try { localStorage.setItem("sm_screen", name); } catch (e) {}
  }

  function uploadFile(file) {
    var fd = new FormData();
    fd.append("file", file);
    api("/api/upload", { method: "POST", body: fd }).then(function (res) {
      state.sessionId = res.session_id;
      state.filename = res.filename;
      state.previewRows = 6;
      state.previewCol = "";
      state.crossGroup = "";
      state.crossTarget = "";
      try { localStorage.setItem("sm_session", res.session_id); localStorage.setItem("sm_file", res.filename); } catch (e) {}
      loadAll().then(function () { smShowScreen("overview"); });
    }).catch(showError);
  }

  function bindUpload() {
    var input = document.createElement("input");
    input.type = "file";
    input.accept = ".csv,.xlsx,.xls";
    input.style.display = "none";
    document.body.appendChild(input);
    input.addEventListener("change", function () {
      if (input.files.length) uploadFile(input.files[0]);
      input.value = "";
    });

    /* sidebar "上传" step now navigates to the import screen */
    var uploadStep = $('.step[data-screen="upload"]');
    if (uploadStep) {
      uploadStep.addEventListener("click", function () { smShowScreen("upload"); });
      bindDropTarget(uploadStep, function (on) {
        uploadStep.style.background = on ? "var(--accent-soft)" : "";
        uploadStep.style.boxShadow = on ? "inset 0 0 0 1px var(--accent-line)" : "";
      });
    }

    /* import screen dropzone: click anywhere opens the picker; drops upload */
    var dropzone = $("#dropzone");
    if (dropzone) {
      dropzone.addEventListener("click", function () { input.click(); });
      bindDropTarget(dropzone, function (on) {
        dropzone.style.borderColor = on ? "var(--accent)" : "var(--accent-line)";
        dropzone.style.background = on ? "var(--accent-soft)" : "var(--surface-2)";
      });
    }

    /* manual demo entry (auto-load removed) */
    var demoBtn = $("#demo-btn");
    if (demoBtn) {
      demoBtn.addEventListener("click", function () {
        api("/api/demo", { method: "POST" }).then(function (res) {
          state.sessionId = res.session_id;
          state.filename = res.filename;
          try { localStorage.setItem("sm_session", res.session_id); localStorage.setItem("sm_file", res.filename); } catch (e) {}
          loadAll().then(function () { smShowScreen("overview"); });
        }).catch(showError);
      });
    }

    /* a stray drop outside the targets must not navigate the page away */
    document.addEventListener("dragover", function (e) { e.preventDefault(); });
    document.addEventListener("drop", function (e) { e.preventDefault(); });

    /* overview "re-upload" ghost button → back to the import screen */
    var reup = $("#screen-overview .head-actions .btn.ghost");
    if (reup) reup.addEventListener("click", function () { smShowScreen("upload"); });
  }

  /* shared drag & drop wiring; highlight() toggles token-based inline styles */
  function bindDropTarget(zone, highlight) {
    var depth = 0;
    zone.addEventListener("dragenter", function (e) {
      e.preventDefault();
      depth++;
      highlight(true);
    });
    zone.addEventListener("dragover", function (e) {
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
    });
    zone.addEventListener("dragleave", function () {
      depth = Math.max(0, depth - 1);
      if (depth === 0) highlight(false);
    });
    zone.addEventListener("drop", function (e) {
      e.preventDefault();
      depth = 0;
      highlight(false);
      if (e.dataTransfer && e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
    });
  }

  function showError(err) {
    var chip = $(".topnav .file");
    if (chip) chip.innerHTML = '<span class="dot"></span>' + esc(err && err.message ? err.message : "请求失败 / request failed");
  }

  /* ---------- boot ---------- */

  function loadAll() {
    return Promise.all([
      api("/api/" + state.sessionId + "/overview"),
      api("/api/" + state.sessionId + "/detect"),
      api("/api/" + state.sessionId + "/stats"),
    ]).then(function (res) {
      state.overview = res[0];
      state.detect = res[1];
      state.stats = res[2];
      state.filename = res[0].filename || state.filename;
      renderChrome();
      renderOverview();
      bindPreviewControls();
      renderTypes();
      renderStats();
      renderCrossControls();
      renderExport();
    }).catch(showError);
  }

  function renderEmptyChrome() {
    var chip = $(".topnav .file");
    if (chip) chip.innerHTML = '<span class="dot"></span><span class="zh">未加载数据</span><span class="en">No dataset</span>';
    setText($(".side-foot .fn"), "—");
    var meta = $(".side-foot .meta");
    if (meta) meta.innerHTML = '<span class="zh">等待上传</span><span class="en">awaiting upload</span>';
  }

  function boot() {
    var saved = null;
    try { saved = localStorage.getItem("sm_session"); } catch (e) {}
    if (saved) {
      api("/api/" + saved + "/overview").then(function () {
        state.sessionId = saved;
        try { state.filename = localStorage.getItem("sm_file") || ""; } catch (e) {}
        return loadAll();
      }).catch(function () {
        try { localStorage.removeItem("sm_session"); } catch (e) {}
        renderEmptyChrome();
        smShowScreen("upload");
      });
    } else {
      /* no auto demo — the import screen is the first thing a new visitor sees */
      renderEmptyChrome();
      smShowScreen("upload");
    }

    bindUpload();

    /* re-fetch language-sensitive content when the mockup's language toggle is used */
    $all(".lang button").forEach(function (b) {
      b.addEventListener("click", function () {
        if (state.sessionId) { renderExport(); }
      });
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
