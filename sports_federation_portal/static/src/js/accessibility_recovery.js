/** @odoo-module **/

const FOCUSABLE_SELECTOR = [
    "a[href]",
    "button:not([disabled])",
    "input:not([disabled])",
    "select:not([disabled])",
    "textarea:not([disabled])",
    "[tabindex]:not([tabindex='-1'])",
].join(", ");

const ERROR_SUMMARY_SELECTOR = [
    "[data-accessibility-error]",
    ".o_portal_accessibility_error",
    ".alert.alert-danger[role='alert']",
].join(", ");

function focusFirst(element) {
    const target = element.querySelector(FOCUSABLE_SELECTOR) || element;
    if (!target.hasAttribute("tabindex") && target === element) {
        target.setAttribute("tabindex", "-1");
    }
    target.focus();
    return target;
}

function connectInvalidControls(summary) {
    const container = summary.closest("form") || summary.parentElement;
    if (!container) {
        return;
    }

    const controls = container.querySelectorAll(
        ".is-invalid, [data-invalid], [aria-invalid='true']"
    );
    controls.forEach((control) => {
        control.setAttribute("aria-invalid", "true");
        const describedBy = new Set(
            (control.getAttribute("aria-describedby") || "").split(" ").filter(Boolean)
        );
        describedBy.add(summary.id);
        control.setAttribute("aria-describedby", [...describedBy].join(" "));
    });
}

function recoverError(errorElement) {
    if (!errorElement) {
        return;
    }
    if (!errorElement.id) {
        errorElement.id = `portal-error-summary-${
            document.querySelectorAll(ERROR_SUMMARY_SELECTOR).length
        }`;
    }
    errorElement.setAttribute("role", "alert");
    errorElement.setAttribute("tabindex", "-1");
    errorElement.setAttribute("aria-live", "assertive");
    connectInvalidControls(errorElement);
    errorElement.focus();
}

function prepareModal(modal) {
    if (!modal) {
        return;
    }
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    focusFirst(modal);
}

function recoverAccessibility(root = document) {
    root.querySelectorAll(ERROR_SUMMARY_SELECTOR).forEach(recoverError);
}

document.addEventListener("DOMContentLoaded", () => recoverAccessibility());

document.addEventListener("shown.bs.modal", (event) => {
    prepareModal(event.target);
});

document.addEventListener("hidden.bs.modal", (event) => {
    const modalTrigger = event.target.__accessibilityOpener;
    if (modalTrigger && document.contains(modalTrigger)) {
        modalTrigger.focus();
    }
});

document.addEventListener("show.bs.modal", (event) => {
    event.target.__accessibilityOpener = document.activeElement;
});

document.addEventListener("portal:accessibility-error", (event) => {
    recoverError(event.detail?.element || event.target);
});

export { recoverAccessibility, recoverError, prepareModal };
