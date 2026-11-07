// DOM helpers shared by every view's render function. Text always goes in
// through textContent, never innerHTML - a vault value is never parsed as
// markup.
function h(tag, attrs, kids) {
  var node = document.createElement(tag);
  if (attrs) Object.keys(attrs).forEach(function (k) {
    if (k === "class") node.className = attrs[k];
    else if (k === "text") node.textContent = attrs[k];
    else node.setAttribute(k, attrs[k]);
  });
  (kids || []).forEach(function (kid) {
    if (kid == null || kid === false) return;
    node.appendChild(typeof kid === "string" ? document.createTextNode(kid) : kid);
  });
  return node;
}

function root() {
  var r = document.getElementById("vr-root");
  r.textContent = "";
  return r;
}

function normalizeResult(data) {
  if (Array.isArray(data)) return { result: data };
  if (!data || typeof data !== "object") return null;
  if (data.structuredContent) {
    var structured = normalizeResult(data.structuredContent);
    if (structured) return structured;
  }
  if (data.result !== undefined) {
    if (Array.isArray(data.result)) return data;
    var nested = normalizeResult(data.result);
    if (nested) return nested;
  }
  return Object.keys(data).length ? data : null;
}

// Some hosts wrap the tool result again, or forward only its JSON text block.
function sc(params) {
  var structured = normalizeResult(params && params.structuredContent);
  if (structured) return structured;
  var blocks = (params && params.content) || [];
  for (var i = 0; i < blocks.length; i++) {
    if (blocks[i].type !== "text") continue;
    try {
      var parsed = normalizeResult(JSON.parse(blocks[i].text));
      if (parsed) return parsed;
    } catch (e) { /* not JSON */ }
  }
  return {};
}

function count(n, one, many) { return n + " " + (n === 1 ? one : many); }

function field(label, value) {
  if (value == null || value === "") return null;
  if (Array.isArray(value)) { if (!value.length) return null; value = value.join(", "); }
  return h("div", { class: "vr-field" }, [
    h("span", { class: "vr-key", text: label }),
    h("span", { class: "vr-val", text: String(value) })
  ]);
}

function metaRow(parts) {
  return h("div", { class: "vr-row-meta" }, parts.filter(Boolean).map(function (t) {
    return h("span", { text: t });
  }));
}
