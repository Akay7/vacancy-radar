// list_vacancies: rows grouped by status, in the order the result already
// has them. Reads only VacancySummary fields.
window.__render = function (params) {
  var rows = sc(params).result || [];
  var r = root();
  if (!rows.length) { r.appendChild(h("p", { class: "vr-empty", text: "No vacancies." })); return; }
  r.appendChild(h("h1", { text: count(rows.length, "vacancy", "vacancies") }));
  var groups = {};
  var order = [];
  rows.forEach(function (row) {
    if (!groups[row.status]) { groups[row.status] = []; order.push(row.status); }
    groups[row.status].push(row);
  });
  order.forEach(function (status) {
    r.appendChild(h("h2", { text: status }));
    r.appendChild(h("ul", { class: "vr-list" }, groups[status].map(function (row) {
      return h("li", { class: "vr-row" }, [
        h("div", { class: "vr-row-main" }, [
          h("span", { class: "vr-role", text: row.role }),
          h("span", { class: "vr-company", text: row.company })
        ]),
        metaRow([
          row.id,
          row.applied_date ? "applied " + row.applied_date : null,
          "active " + row.last_activity,
          count(row.document_count, "doc", "docs")
        ])
      ]);
    })));
  });
};
