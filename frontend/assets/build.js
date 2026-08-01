/* SurveyMind · Survey Design screen (#screen-build)
 *
 * Self-contained data layer, same conventions as insight.js: its own closure,
 * its own API resolution, localStorage for anything shared, no changes to
 * data.js and no changes to any existing screen's DOM.
 *
 * On honesty about what generated the questionnaire
 * -------------------------------------------------
 * The LLM author is a later batch. Until then every draft comes from a bundled
 * template, and the API says so in `generation_mode`. This screen renders that
 * field rather than deciding for itself — no "Generate with AI" button that
 * quietly runs a template underneath, because a reader who found that out later
 * would be right to distrust everything else on the page.
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

  var cache = { draftId: null, draft: null, templates: null, loading: false };

  /* ---------- helpers (mirrors of the ones in insight.js) ---------- */

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function api(path, opts) {
    return fetch(API + path, opts).then(function (r) {
      if (!r.ok) { return r.json().catch(function () { return {}; }).then(function (b) { throw new Error(b.detail || ("HTTP " + r.status)); }); }
      return r.json();
    });
  }

  function lang() { return document.body.getAttribute("data-lang") === "en" ? "en" : "zh"; }
  function apiLang() { return lang() === "en" ? "en" : "zh-CN"; }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function dual(zhHTML, enHTML) {
    return '<span class="zh">' + zhHTML + '</span><span class="en">' + enHTML + "</span>";
  }

  function localized(value, fallback) {
    if (!value) return fallback || "";
    return { zh: value["zh-CN"] || value.en || "", en: value.en || value["zh-CN"] || "" };
  }

  function dualFrom(value, fallback) {
    var t = localized(value, fallback);
    if (typeof t === "string") return esc(t);
    return dual(esc(t.zh), esc(t.en));
  }

  /* ---------- vocabulary ---------- */

  var TYPE_SHORT = {
    "scale question": "scale",
    "single-choice question": "single",
    "multiple-choice question": "multi",
    "numeric question": "num",
    "open-ended text question": "open",
  };
  var TYPE_ZH = { num: "数值", scale: "量表", single: "单选", multi: "多选", open: "开放" };
  var TYPE_EN = { num: "Numeric", scale: "Scale", single: "Single", multi: "Multi", open: "Open" };

  function typeBadge(questionType) {
    var short = TYPE_SHORT[questionType] || "num";
    return '<span class="tb ' + short + '"><span class="d"></span><span class="zh">' +
      TYPE_ZH[short] + '</span><span class="en">' + TYPE_EN[short] + "</span></span>";
  }

  var SEVERITY_CLASS = { error: "warn", warning: "warn", info: "info" };
  var SEVERITY_LABEL = {
    error: { zh: "错误", en: "Error" },
    warning: { zh: "提示", en: "Warning" },
    info: { zh: "备注", en: "Note" },
  };

  var ICONS = {
    warn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"></path></svg>',
    info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 16v-4M12 8h.01"></path><circle cx="12" cy="12" r="9"></circle></svg>',
    good: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 17l6-6 4 4 8-8"></path></svg>',
  };

  var EXPORTS = [
    { format: "template_csv", zh: "空白模板 CSV", en: "Blank template CSV", primary: false },
    { format: "sample_csv", zh: "示例数据 CSV", en: "Sample data CSV", primary: false },
    { format: "questionnaire_md", zh: "问卷文档 MD", en: "Questionnaire MD", primary: false },
    { format: "codebook_md", zh: "变量编码表 MD", en: "Codebook MD", primary: false },
    { format: "schema_json", zh: "schema.json", en: "schema.json", primary: true },
  ];

  /* ---------- rendering ---------- */

  function renderTemplates() {
    var wrap = $("#bld-templates");
    if (!wrap || !cache.templates) return;
    wrap.innerHTML = cache.templates.map(function (t) {
      var active = cache.draft && cache.draft.generation && cache.draft.generation.template === t.key;
      return '<button class="bld-template" data-key="' + esc(t.key) + '" ' +
        'style="text-align:left;border:1px solid ' + (active ? "var(--accent)" : "var(--line)") +
        ';background:' + (active ? "var(--accent-soft)" : "var(--surface)") +
        ';border-radius:var(--r-md);padding:10px 13px;cursor:pointer;display:flex;' +
        'flex-direction:column;gap:3px;">' +
        '<span style="font-weight:600;font-size:13px;color:var(--ink);">' +
        dualFrom(t.name) + "</span>" +
        '<span style="font-size:11.5px;color:var(--ink-3);line-height:1.45;">' +
        dualFrom(t.description) + "</span></button>";
    }).join("");

    $all(".bld-template", wrap).forEach(function (button) {
      button.addEventListener("click", function () {
        createDraft(button.getAttribute("data-key"));
      });
    });
  }

  function renderModeNote() {
    var box = $("#bld-mode-note");
    if (!box) return;
    if (!cache.draft) { box.innerHTML = ""; return; }
    var generation = cache.draft.generation || {};
    var source = $("#bld-source");
    if (source) source.textContent = cache.draft.generation_mode || "template";

    /* Rendered from the API's own field. When the LLM author lands, the mode
       changes there and this follows without a frontend edit. */
    if (cache.draft.generation_mode === "template") {
      box.innerHTML = '<div class="ins info"><span class="ib">' + ICONS.info + "</span>" +
        dual(
          "本问卷由<b>内置模板</b>生成，未调用任何语言模型。AI 撰写功能尚未接入。",
          "Built from a <b>bundled template</b>; no language model was called. AI authoring is not wired up yet."
        ) + "</div>";
    } else {
      box.innerHTML = '<div class="ins good"><span class="ib">' + ICONS.good + "</span>" +
        dual("由 AI 生成，已通过方法学校验。", "Generated by the AI author and checked against the methodology rules.") +
        "</div>";
    }
    var used = generation.llm_used;
    if (used === true && cache.draft.generation_mode === "template") {
      /* Contradictory state: say so rather than pick one. */
      box.innerHTML += '<div class="ins warn"><span class="ib">' + ICONS.warn + "</span>" +
        dual("生成来源标记不一致，请检查后端。", "The generation source flags disagree; check the API.") + "</div>";
    }
  }

  function questions(draft) {
    var out = [];
    (draft.survey.sections || []).forEach(function (section) {
      (section.questions || []).forEach(function (q) { out.push({ section: section, question: q }); });
    });
    return out;
  }

  function renderMetrics() {
    var draft = cache.draft;
    if (!draft) return;
    var metrics = $all("#bld-metrics .metric");
    var items = questions(draft);
    var counts = draft.validation.counts;

    if (metrics[0]) {
      $(".v", metrics[0]).textContent = items.length;
      var scale = items.filter(function (i) { return i.question.question_type === "scale question"; }).length;
      $(".foot", metrics[0]).innerHTML = dual(
        "其中 " + scale + " 道量表题", scale + " scale items");
    }
    if (metrics[1]) {
      var v = $(".v", metrics[1]);
      v.textContent = counts.error;
      v.style.color = counts.error > 0 ? "var(--warn)" : "";
      $(".foot", metrics[1]).innerHTML = counts.error === 0
        ? dual("0 个错误 · " + counts.warning + " 条提示", "0 errors · " + counts.warning + " warnings")
        : dual(counts.error + " 个错误需处理", counts.error + " errors to fix");
    }
    if (metrics[2]) {
      var constructs = (draft.survey.constructs || []).length;
      $(".v", metrics[2]).textContent = constructs;
      $(".foot", metrics[2]).innerHTML = dual("每个构念独立计算信度", "reliability computed per construct");
    }
    if (metrics[3]) {
      $(".v", metrics[3]).textContent = draft.analysis_plan.recommended_total_n;
      $(".foot", metrics[3]).innerHTML = dual("满足计划中最严格的一项", "covers the strictest planned analysis");
    }
  }

  function renderStructure() {
    var draft = cache.draft;
    var tbody = $("#bld-structure tbody");
    if (!draft || !tbody) return;
    var items = questions(draft);
    var count = $("#bld-structure-count");
    if (count) count.textContent = items.length;

    var number = 0;
    tbody.innerHTML = items.map(function (entry) {
      number += 1;
      var q = entry.question;
      var flags = [];
      if (q.reverse_coded) flags.push(dual("反向", "reverse"));
      if (q.attention_check) flags.push(dual("注意力", "attention"));
      if (!q.required) flags.push(dual("选填", "optional"));
      var flagHTML = flags.map(function (f) {
        return '<span class="pill" style="font-size:10.5px;">' + f + "</span>";
      }).join(" ") || '<span class="mono" style="color:var(--muted);font-size:11px;">—</span>';

      return "<tr>" +
        '<td class="mono" style="color:var(--ink-3);font-size:11.5px;">' + number + "</td>" +
        '<td style="max-width:340px;"><span style="color:var(--ink);font-size:12.5px;line-height:1.45;">' +
        dualFrom(q.text) + "</span></td>" +
        "<td>" + typeBadge(q.question_type) + "</td>" +
        '<td class="mono" style="font-size:11px;color:var(--ink-3);">' +
        esc(q.construct_id || "—") + "</td>" +
        "<td>" + flagHTML + "</td>" +
        '<td class="mono" style="font-size:11px;color:var(--ink-3);">' + esc(q.code) + "</td>" +
        "</tr>";
    }).join("");
  }

  function renderIssues() {
    var draft = cache.draft;
    var wrap = $("#bld-issues");
    if (!draft || !wrap) return;
    var issues = draft.validation.issues || [];
    var count = $("#bld-issues-count");
    if (count) count.textContent = issues.length;

    if (!issues.length) {
      wrap.innerHTML = '<div class="ins good"><span class="ib">' + ICONS.good + "</span>" +
        dual("未发现方法学问题。", "No methodology issues found.") + "</div>";
      return;
    }
    wrap.innerHTML = issues.map(function (issue) {
      var cls = SEVERITY_CLASS[issue.severity] || "info";
      var label = SEVERITY_LABEL[issue.severity] || SEVERITY_LABEL.info;
      var target = issue.target_id ? '<span class="mono" style="font-size:10.5px;opacity:.7;"> · ' + esc(issue.target_id) + "</span>" : "";
      var suggestion = (issue.suggestion && (issue.suggestion["zh-CN"] || issue.suggestion.en))
        ? '<div style="margin-top:4px;font-size:11px;color:var(--ink-3);line-height:1.5;">' +
          dualFrom(issue.suggestion) + "</div>"
        : "";
      return '<div class="ins ' + cls + '"><span class="ib">' + ICONS[cls] + "</span><div>" +
        '<span class="pill" style="font-size:10.5px;margin-right:6px;">' +
        dual(esc(label.zh), esc(label.en)) + "</span>" +
        dualFrom(issue.message) + target + suggestion + "</div></div>";
    }).join("");
  }

  var METHOD_LABEL = {
    cronbach_alpha: { zh: "Cronbach's α", en: "Cronbach's alpha" },
    independent_t_test: { zh: "独立样本 t 检验", en: "Independent t test" },
    one_way_anova: { zh: "单因素 ANOVA", en: "One-way ANOVA" },
    mann_whitney_u: { zh: "Mann-Whitney U", en: "Mann-Whitney U" },
    kruskal_wallis: { zh: "Kruskal-Wallis", en: "Kruskal-Wallis" },
    ordinal_association: { zh: "有序关联 (Somers' D)", en: "Ordinal association (Somers' D)" },
    chi_square_independence: { zh: "卡方独立性检验", en: "Chi-square" },
    pearson_correlation: { zh: "Pearson 相关", en: "Pearson correlation" },
    multi_select_frequency: { zh: "多选频次", en: "Multi-select frequency" },
  };

  function renderPlan() {
    var draft = cache.draft;
    var tbody = $("#bld-plan tbody");
    if (!draft || !tbody) return;
    var analyses = draft.analysis_plan.analyses || [];
    var count = $("#bld-plan-count");
    if (count) count.textContent = analyses.length;

    tbody.innerHTML = analyses.map(function (a) {
      var label = METHOD_LABEL[a.method] || { zh: a.method, en: a.method };
      return "<tr>" +
        "<td>" + dual(esc(label.zh), esc(label.en)) + "</td>" +
        '<td class="mono" style="font-size:11px;color:var(--ink-3);">' + esc(a.target) + "</td>" +
        '<td class="num-cell">' + (a.min_n === null || a.min_n === undefined ? "—" : a.min_n) + "</td>" +
        "</tr>";
    }).join("");
  }

  function renderExports() {
    var wrap = $("#bld-exports");
    if (!wrap || !cache.draftId) return;
    wrap.innerHTML = EXPORTS.map(function (e) {
      return '<button class="btn ' + (e.primary ? "primary" : "ghost") + '" data-format="' +
        esc(e.format) + '">' + dual(esc(e.zh), esc(e.en)) + " ↓</button>";
    }).join("");
    $all("button[data-format]", wrap).forEach(function (button) {
      button.addEventListener("click", function () {
        var format = button.getAttribute("data-format");
        window.open(
          API + "/api/gen/" + cache.draftId + "/export?format=" + encodeURIComponent(format) +
          "&language=" + encodeURIComponent(apiLang()) + "&download=true",
          "_blank"
        );
      });
    });
  }

  function renderAll() {
    renderTemplates();
    renderModeNote();
    renderMetrics();
    renderStructure();
    renderIssues();
    renderPlan();
    renderExports();
  }

  function showError(err) {
    var box = $("#bld-mode-note");
    if (box) {
      box.innerHTML = '<div class="ins warn"><span class="ib">' + ICONS.warn + "</span>" +
        dual("请求失败：" + esc(err.message), "Request failed: " + esc(err.message)) + "</div>";
    }
  }

  /* ---------- loading ---------- */

  function rememberDraft(id) {
    cache.draftId = id;
    try { localStorage.setItem("sm_draft", id); } catch (e) {}
  }

  function createDraft(templateKey) {
    api("/api/gen/drafts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ template: templateKey, language: apiLang() }),
    }).then(function (draft) {
      cache.draft = draft;
      rememberDraft(draft.draft_id);
      renderAll();
      /* The schema is the thing that has to travel with the responses, so it is
         offered immediately rather than waiting to be found in the export row. */
      window.open(
        API + "/api/gen/" + draft.draft_id + "/export?format=schema_json&download=true",
        "_blank"
      );
    }).catch(showError);
  }

  function ensureLoaded() {
    if (cache.loading) return;
    cache.loading = true;

    var saved = null;
    try { saved = localStorage.getItem("sm_draft"); } catch (e) {}

    api("/api/gen/templates").then(function (body) {
      cache.templates = body.templates;
      renderTemplates();
      if (!saved) { cache.loading = false; return null; }
      /* A draft lives 24 hours, so a reader who comes back the same day picks
         up where they left off. A 404 just means it expired. */
      return api("/api/gen/" + saved).then(function (draft) {
        cache.draft = draft;
        rememberDraft(draft.draft_id);
        renderAll();
      }).catch(function () {
        try { localStorage.removeItem("sm_draft"); } catch (e) {}
      });
    }).then(function () {
      cache.loading = false;
    }).catch(function (err) {
      cache.loading = false;
      showError(err);
    });
  }

  /* ---------- boot ---------- */

  function boot() {
    var step = $('.step[data-screen="build"]');
    if (step) step.addEventListener("click", ensureLoaded);
    document.addEventListener("click", function (e) {
      if (e.target.closest('[data-go="build"]')) ensureLoaded();
    });

    var screen = $("#screen-build");
    if (screen && screen.classList.contains("active")) ensureLoaded();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
