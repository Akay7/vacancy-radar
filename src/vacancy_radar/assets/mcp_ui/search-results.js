// search: the ranked hits, each drawn from its own SearchHit fields. The
// snippet is part of the result - a hit never carries a full document body,
// so neither does this view.
window.__render = function (params) {
  var d = sc(params);
  var hits = d.hits || [];
  var r = root();
  var heading = count(hits.length, "result", "results");
  if (d.mode) heading += " · " + d.mode;
  r.appendChild(h("h1", { text: heading }));
  if (!hits.length) { r.appendChild(h("p", { class: "vr-empty", text: "No matches." })); return; }
  r.appendChild(h("ul", { class: "vr-list" }, hits.map(function (hit) {
    var score = typeof hit.score === "number" ? hit.score.toFixed(3) : hit.score;
    return h("li", { class: "vr-row" }, [
      h("div", { class: "vr-row-main" }, [
        h("span", { class: "vr-role", text: hit.role + " · " + hit.company }),
        h("span", { class: "vr-chip", text: hit.kind })
      ]),
      hit.snippet ? h("p", { class: "vr-snippet", text: hit.snippet }) : null,
      metaRow(["score " + score, String(hit.date), hit.path])
    ]);
  })));
};
