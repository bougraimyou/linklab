/* LinkLab web UI. No framework: the whole thing is a form, a fetch, and a
   table of the line items. */
(function () {
  "use strict";

  var medium = "fiber";
  var reference = null;
  var project = null;

  function el(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s === null || s === undefined ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* -- view switching ------------------------------------------------- */
  document.querySelectorAll("nav.tabs button").forEach(function (b) {
    b.addEventListener("click", function () {
      document.querySelectorAll("nav.tabs button").forEach(function (x) { x.classList.remove("on"); });
      b.classList.add("on");
      ["calculator", "project", "reference"].forEach(function (v) {
        el("view-" + v).hidden = (v !== b.dataset.view);
      });
      if (b.dataset.view === "project") loadProject();
      if (b.dataset.view === "reference") loadReference();
    });
  });

  /* -- medium tabs ---------------------------------------------------- */
  document.querySelectorAll('[data-tabs="medium"] button').forEach(function (b) {
    b.addEventListener("click", function () {
      document.querySelectorAll('[data-tabs="medium"] button').forEach(function (x) { x.classList.remove("on"); });
      b.classList.add("on");
      medium = b.dataset.target;
      document.querySelectorAll('[data-panel^="medium-"]').forEach(function (p) {
        p.hidden = (p.getAttribute("data-panel") !== "medium-" + medium);
      });
      compute();
    });
  });

  /* -- reference data ------------------------------------------------- */
  function loadReference() {
    if (reference) { renderReference(); return; }
    fetch("/api/reference").then(function (r) { return r.json(); }).then(function (d) {
      reference = d; renderReference();
    });
  }

  function renderReference() {
    var d = reference;
    var fibres = Object.keys(d.fibres).map(function (k) {
      var f = d.fibres[k];
      var att = Object.keys(f.attenuation).map(function (w) {
        return w + " nm: " + f.attenuation[w] + " dB/km";
      }).join(", ");
      return "<tr><td class='mono'>" + esc(k) + "</td><td>" + esc(f.label) + "</td><td class='small'>" +
        esc(att) + "</td><td class='num'>" + esc(f.dispersion) + "</td></tr>";
    }).join("");
    var copper = Object.keys(d.copper).map(function (k) {
      var c = d.copper[k];
      return "<tr><td class='mono'>" + esc(k) + "</td><td>" + esc(c.label) + "</td><td class='num'>" +
        esc(c.channel_max_m) + " m</td><td class='num'>" + esc(c.permanent_link_max_m) + " m</td><td class='num'>" +
        esc(c.max_insertion_loss_db) + " dB</td><td class='num'>" + esc(c.spec_frequency_mhz) + " MHz</td></tr>";
    }).join("");
    el("reference").innerHTML =
      "<h2>Fibre types</h2><div class='card'><table><thead><tr><th>Key</th><th>Type</th><th>Attenuation</th>" +
      "<th class='num'>Dispersion ps/(nm&middot;km)</th></tr></thead><tbody>" + fibres + "</tbody></table></div>" +
      "<h2>Copper categories</h2><div class='card'><table><thead><tr><th>Key</th><th>Category</th>" +
      "<th class='num'>Channel</th><th class='num'>Permanent</th><th class='num'>Max IL</th><th class='num'>Spec freq</th>" +
      "</tr></thead><tbody>" + copper + "</tbody></table></div>" +
      "<h2>Free space path loss reference</h2><div class='card'><p class='small muted'>" +
      "1 km at 1 GHz &rarr; <strong>" + esc(d.fspl_example["1km_1GHz"]) + " dB</strong><br>" +
      "100 m at 1550 nm &rarr; <strong>" + esc(d.fspl_example["100m_1550nm"]) + " dB</strong></p>" +
      "<p class='small muted'>FSPL is a radio-propagation term. It is used in the microwave " +
      "budget and deliberately <strong>not</strong> in the fibre budget, because light inside a " +
      "glass core does not suffer free-space spreading.</p></div>";
  }

  /* -- calculator ------------------------------------------------------ */
  function formValues(form) {
    var out = {};
    Array.prototype.forEach.call(form.elements, function (e) {
      if (!e.name) return;
      var v = e.value;
      if (e.type === "number") {
        out[e.name] = v === "" ? null : parseFloat(v);
      } else {
        out[e.name] = v;
      }
    });
    return out;
  }

  function compute() {
    var form = el("form-" + medium);
    if (!form) return;
    var body = formValues(form);
    // The media selects are filled from /api/reference; until that lands they
    // are empty, and an empty media key is a 400, not a useful result.
    if (medium === "fiber" && !body.fibre) return;
    if (medium === "copper" && !body.category) return;
    body.medium = medium;
    fetch("/api/budget", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json(); }).then(render).catch(function (e) {
      el("result").innerHTML = "<p class='muted'>" + esc(e) + "</p>";
    });
  }

  function render(d) {
    if (d.error) { el("result").innerHTML = "<p class='muted'>" + esc(d.error) + "</p>"; return; }
    var lines = [];
    function row(label, value) {
      if (value === null || value === undefined) return;
      lines.push("<tr><td>" + label + "</td><td>" + value + "</td></tr>");
    }
    var total = 0;
    if (medium === "copper") {
      row("Length", d.length_m.toFixed(1) + " m");
      row("Channel limit", d.channel_max_m + " m");
      row("Permanent link limit", d.permanent_link_max_m + " m");
      row("Insertion loss", d.insertion_loss_db.toFixed(2) + " dB");
      row("Derating", d.derating_db.toFixed(2) + " dB");
      row("PS-NEXT penalty", d.ps_next_penalty_db.toFixed(2) + " dB");
      total = d.total_budget_db;
      row("Total budget", total.toFixed(2) + " dB");
      row("Allowed", d.max_insertion_loss_db.toFixed(1) + " dB");
    } else if (medium === "microwave") {
      row("Free space path loss", d.fspl_db.toFixed(2) + " dB");
      row("EIRP", d.eirp_dbm.toFixed(2) + " dBm");
      row("Received level", d.received_level_dbm.toFixed(2) + " dBm");
      row("Receiver threshold", d.rx_threshold_dbm.toFixed(2) + " dBm");
      total = d.margin_db;
      row("Margin", total.toFixed(2) + " dB");
      row("Required", d.required_margin_db.toFixed(2) + " dB");
    } else {
      row("Length", d.length_km.toFixed(3) + " km");
      row("Attenuation", d.attenuation_db_per_km.toFixed(3) + " dB/km");
      row("Fibre loss", d.fiber_loss_db.toFixed(3) + " dB");
      row("Splices", d.splice_loss_db.toFixed(3) + " dB");
      row("Connectors", d.connector_loss_db.toFixed(3) + " dB");
      total = d.total_loss_db;
      row("Total loss", total.toFixed(3) + " dB");
      row("Available budget", d.available_budget_db.toFixed(3) + " dB");
      row("Margin", d.margin_db.toFixed(3) + " dB");
      if (d.dispersion_limit_km !== null) {
        row("Dispersion", d.dispersion_ps.toFixed(1) + " ps");
        row("Dispersion limit", d.dispersion_limit_km.toFixed(2) + " km");
        row("Dispersion penalty", d.dispersion_penalty_db.toFixed(3) + " dB");
      }
      if (d.modal_limit_km !== null) row("Modal bandwidth limit", d.modal_limit_km.toFixed(3) + " km");
      row("Max reach", d.max_reach_km.toFixed(3) + " km");
    }
    var ok = d.verdict === "PASS";
    var notes = (d.notes || []).map(function (n) {
      return "<div class='finding'>" + esc(n) + "</div>";
    }).join("");
    el("result").innerHTML =
      "<div style='display:flex;align-items:center;gap:12px;margin-bottom:6px'>" +
      "<span class='pill " + (ok ? "ok" : "bad") + "'>" + esc(d.verdict) + "</span>" +
      (d.limiting_factor && d.limiting_factor !== "none"
        ? "<span class='muted small'>limited by " + esc(d.limiting_factor) + "</span>" : "") +
      "</div>" +
      "<table class='lines'>" + lines.join("") + "</table>" + notes;
  }

  /* -- project --------------------------------------------------------- */
  function loadProject() {
    if (project) { renderProject(); return; }
    fetch("/api/project").then(function (r) { return r.json(); }).then(function (d) {
      project = d; renderProject();
    });
  }

  function renderProject() {
    var d = project;
    var findings = (d.findings || []).map(function (f) {
      return "<div class='finding" + (f.severity === "warning" ? " warn" : "") + "'><strong>" +
        esc(f.code) + "</strong> &mdash; " + esc(f.message) +
        (f.where ? " (" + esc(f.where) + ")" : "") + "</div>";
    }).join("");
    var cables = d.cables.map(function (c) {
      return "<tr><td class='mono'>" + esc(c.id) + "</td><td>" + esc(c.a_end) + "</td><td>" + esc(c.b_end) +
        "</td><td class='mono'>" + esc(c.media) + "</td><td class='num'>" + c.length_m.toFixed(1) + " m</td></tr>";
    }).join("");
    var spans = d.spans.map(function (s) {
      return "<tr><td class='mono'>" + esc(s.id) + "</td><td>" + esc(s.a_end) + "</td><td>" + esc(s.b_end) +
        "</td><td class='mono'>" + esc(s.fibre) + "</td><td class='num'>" + s.length_km.toFixed(2) + " km</td>" +
        "<td class='num'>" + esc(s.tx_power_dbm) + " / " + esc(s.rx_sensitivity_dbm) + " dBm</td></tr>";
    }).join("");
    var racks = d.racks.map(function (r) {
      return "<tr><td class='mono'>" + esc(r.id) + "</td><td>" + esc(r.name) + "</td><td class='muted'>" +
        esc(r.location) + "</td><td class='num'>" + r.u_height + "U</td><td class='num'>" + r.panels.length + "</td></tr>";
    }).join("");
    el("project-summary").innerHTML =
      "<h2>" + esc(d.name) + "</h2><p class='muted small'>" + esc(d.client) + " &middot; " + esc(d.site) + "</p>" +
      "<div class='card'><table><thead><tr><th>ID</th><th>Rack</th><th>Location</th><th class='num'>Height</th>" +
      "<th class='num'>Panels</th></tr></thead><tbody>" + racks + "</tbody></table></div>";
    el("project-findings").innerHTML = findings
      ? "<h2>Design findings</h2>" + findings : "";
    el("project-cables").innerHTML =
      "<h2>Cable schedule</h2><div class='card'><table><thead><tr><th>ID</th><th>A end</th><th>B end</th>" +
      "<th>Media</th><th class='num'>Length</th></tr></thead><tbody>" + cables + "</tbody></table></div>";
    el("project-spans").innerHTML =
      "<h2>Optical spans</h2><div class='card'><table><thead><tr><th>ID</th><th>A end</th><th>B end</th>" +
      "<th>Fibre</th><th class='num'>Length</th><th class='num'>Tx / Rx</th></tr></thead><tbody>" +
      spans + "</tbody></table></div>";
  }

  /* -- boot ------------------------------------------------------------ */
  fetch("/api/reference").then(function (r) { return r.json(); }).then(function (d) {
    reference = d;
    var fs = el("fibre-select");
    fs.innerHTML = Object.keys(d.fibres).map(function (k) {
      return "<option value='" + esc(k) + "'>" + esc(d.fibres[k].label) + "</option>";
    }).join("");
    var cs = el("copper-select");
    cs.innerHTML = Object.keys(d.copper).map(function (k) {
      return "<option value='" + esc(k) + "'>" + esc(d.copper[k].label) + "</option>";
    }).join("");
    compute();
  });

  Array.prototype.forEach.call(document.querySelectorAll("#form-fiber input, #form-fiber select"), function (e) {
    e.addEventListener("input", compute);
    e.addEventListener("change", compute);
  });
  Array.prototype.forEach.call(document.querySelectorAll("#form-microwave input, #form-microwave select"), function (e) {
    e.addEventListener("input", compute);
    e.addEventListener("change", compute);
  });
  Array.prototype.forEach.call(document.querySelectorAll("#form-copper input, #form-copper select"), function (e) {
    e.addEventListener("input", compute);
    e.addEventListener("change", compute);
  });

  compute();
})();
