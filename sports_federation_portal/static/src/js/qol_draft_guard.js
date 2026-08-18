/** @odoo-module **/
const selector = "form[data-qol-draft-guard='1']";
let dirty = false;
document.addEventListener("input", (event) => { if (event.target.closest(selector)) dirty = true; });
document.addEventListener("submit", (event) => { if (event.target.matches(selector)) dirty = false; });
window.addEventListener("beforeunload", (event) => { if (dirty) { event.preventDefault(); event.returnValue = ""; } });
