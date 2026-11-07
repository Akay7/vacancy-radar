// get_company: the company's own metadata, any warnings the dossier carries,
// then its vacancies as summaries.
window.__render = function (params) {
  var d = sc(params);
  var r = root();
  if (!d || !d.slug) { r.appendChild(h("p", { class: "vr-empty", text: "No company." })); return; }
  r.appendChild(h("header", { class: "vr-head" }, [
    h("h1", { text: d.name || d.slug }),
    h("div", { class: "vr-sub" }, [ h("span", { class: "vr-id", text: d.slug }) ])
  ]));
  r.appendChild(h("section", { class: "vr-meta" }, [
    field("Domains", d.domains),
    field("Recruiters", d.recruiters),
    field("Notes", d.notes)
  ].filter(Boolean)));
  (d.warnings || []).forEach(function (w) {
    r.appendChild(h("p", { class: "vr-warn", text: w }));
  });
  var vs = d.vacancies || [];
  r.appendChild(h("h2", { text: count(vs.length, "vacancy", "vacancies") }));
  r.appendChild(h("ul", { class: "vr-list" }, vs.map(function (row) {
    return h("li", { class: "vr-row" }, [
      h("div", { class: "vr-row-main" }, [
        h("span", { class: "vr-role", text: row.role }),
        h("span", { class: "vr-chip", text: row.status })
      ]),
      metaRow([
        row.id,
        row.applied_date ? "applied " + row.applied_date : null,
        count(row.document_count, "doc", "docs")
      ])
    ]);
  })));
};
