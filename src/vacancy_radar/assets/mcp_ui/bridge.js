// The ext-apps host<->iframe handshake, shared verbatim by every view.
// JSON-RPC 2.0 over postMessage to window.parent: ui/initialize ->
// ui/notifications/initialized, then render on ui/notifications/tool-result,
// re-theme on ui/notifications/host-context-changed, and report height with
// ui/notifications/size-changed after each render. A view supplies
// window.__render(params), where params is the tool-result params object
// ({content, structuredContent}).
(function () {
  var PROTOCOL_VERSION = "2026-01-26";
  var initId = 1;

  function post(msg) {
    msg.jsonrpc = "2.0";
    window.parent.postMessage(msg, "*");
  }

  function applyTheme(ctx) {
    if (ctx && typeof ctx.theme === "string") {
      document.documentElement.setAttribute("data-theme", ctx.theme);
    }
  }

  function reportSize() {
    post({
      method: "ui/notifications/size-changed",
      params: { height: document.documentElement.scrollHeight }
    });
  }

  function render(params) {
    try {
      window.__render(params || {});
    } catch (err) {
      var pre = document.createElement("pre");
      pre.className = "vr-error";
      pre.textContent = String(err && err.stack ? err.stack : err);
      document.body.appendChild(pre);
    }
    reportSize();
  }

  window.addEventListener("message", function (event) {
    var msg = event.data;
    if (!msg || msg.jsonrpc !== "2.0") return;
    if (msg.id === initId && msg.result) {
      applyTheme(msg.result.hostContext);
      post({ method: "ui/notifications/initialized", params: {} });
    } else if (msg.method === "ui/notifications/tool-result") {
      render(msg.params);
    } else if (msg.method === "ui/notifications/host-context-changed") {
      applyTheme(msg.params);
    }
  });

  post({
    id: initId,
    method: "ui/initialize",
    params: {
      protocolVersion: PROTOCOL_VERSION,
      clientInfo: { name: "vacancy-radar", version: "0" },
      capabilities: {},
      appCapabilities: { availableDisplayModes: ["inline"] }
    }
  });
})();
