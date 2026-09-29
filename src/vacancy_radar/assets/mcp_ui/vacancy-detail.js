// get_vacancy: the record's own fields plus its document index - paths and
// titles only. VacancyDetail carries no document body and no status history,
// so this view shows neither.
window.__render = function (params) {
  var d = sc(params);
  var r = root();
  if (!d || !d.id) { r.appendChild(h("p", { class: "vr-empty", text: "No vacancy." })); return; }
  r.appendChild(h("header", { class: "vr-head" }, [
    h("h1", { text: d.role || "(unknown role)" }),
    h("div", { class: "vr-sub" }, [
      h("span", { class: "vr-company", text: d.company }),
      h("span", { class: "vr-chip", text: d.status })
    ])
  ]));
  r.appendChild(h("section", { class: "vr-meta" }, [
    field("ID", d.id),
    field("Source", d.source_url),
    field("Found", d.found_date),
    field("Applied", d.applied_date),
    field("Recruiter", d.recruiter),
    field("Stage note", d.stage_note),
    field("Salary note", d.salary_note),
    field("External ID", d.external_id),
    field("Tags", d.tags)
  ].filter(Boolean)));
  var docs = d.documents || [];
  r.appendChild(h("h2", { text: count(docs.length, "document", "documents") }));
  if (docs.length) {
    r.appendChild(h("ul", { class: "vr-list" }, docs.map(function (doc) {
      return h("li", { class: "vr-row" }, [
        h("div", { class: "vr-row-main" }, [
          h("span", { class: "vr-role", text: doc.title }),
          h("span", { class: "vr-chip", text: doc.kind })
        ]),
        metaRow([String(doc.date), doc.id, doc.path])
      ]);
    })));
  }
};
