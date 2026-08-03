document.body.addEventListener("click", function (event) {
  const button = event.target.closest(".copy-draft");
  if (!button) return;

  const targetId = button.getAttribute("data-copy-target");
  const target = document.getElementById(targetId);
  if (!target) return;

  navigator.clipboard.writeText(target.textContent);
});
