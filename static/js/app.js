(function () {
    "use strict";

    // ---- Toasts -------------------------------------------------------------
    function ensureToastStack() {
        var stack = document.getElementById("toast-stack");
        if (!stack) {
            stack = document.createElement("div");
            stack.id = "toast-stack";
            stack.className = "toast-stack";
            document.body.appendChild(stack);
        }
        return stack;
    }

    function dismissToast(toast) {
        toast.classList.add("is-leaving");
        setTimeout(function () { toast.remove(); }, 200);
    }

    window.vaultShowToast = function (message, tag) {
        var stack = ensureToastStack();
        var toast = document.createElement("div");
        toast.className = "toast toast-" + (tag || "info");
        toast.setAttribute("role", "status");
        toast.textContent = message;
        stack.appendChild(toast);
        setTimeout(function () { dismissToast(toast); }, 4000);
    };

    document.querySelectorAll(".toast-stack .toast").forEach(function (toast) {
        setTimeout(function () { dismissToast(toast); }, 4000);
    });

    // ---- Shared feed helper (used by composer.js / upload.js) ---------------
    window.vaultAppendItem = function (html) {
        var feed = document.getElementById("item-feed");
        if (!feed) return;
        var emptyState = feed.querySelector(".empty-state");
        if (emptyState) emptyState.remove();
        var wrapper = document.createElement("div");
        wrapper.innerHTML = html.trim();
        var node = wrapper.firstElementChild;
        if (node) {
            feed.appendChild(node);
            node.scrollIntoView({ behavior: "smooth", block: "end" });
        }
    };

    // ---- Header "more options" modal -------------------------------------------
    var optionsToggle = document.querySelector("[data-options-toggle]");
    var optionsModal = document.getElementById("options-modal");
    var optionsClose = document.getElementById("options-modal-close");

    if (optionsToggle && optionsModal && typeof optionsModal.showModal === "function") {
        optionsToggle.addEventListener("click", function () {
            optionsModal.showModal();
        });
        if (optionsClose) {
            optionsClose.addEventListener("click", function () { optionsModal.close(); });
        }
        optionsModal.addEventListener("click", function (event) {
            if (event.target === optionsModal) optionsModal.close();
        });
    }

    // ---- Confirmation modal ---------------------------------------------------
    var modal = document.getElementById("confirm-modal");
    var modalMessage = document.getElementById("confirm-modal-message");
    var modalAccept = document.getElementById("confirm-modal-accept");
    var modalCancel = document.getElementById("confirm-modal-cancel");

    function openConfirmModal(message, onConfirm) {
        if (!modal || typeof modal.showModal !== "function") {
            if (window.confirm(message)) onConfirm();
            return;
        }
        modalMessage.textContent = message;
        modal.showModal();

        function cleanup() {
            modalAccept.removeEventListener("click", onAccept);
            modalCancel.removeEventListener("click", onCancel);
        }
        function onAccept() { cleanup(); modal.close(); onConfirm(); }
        function onCancel() { cleanup(); modal.close(); }

        modalAccept.addEventListener("click", onAccept);
        modalCancel.addEventListener("click", onCancel);
    }

    // ---- Generic AJAX form handling -------------------------------------------
    // Covers favorite toggle / delete / restore / permanent-delete: the server
    // returns either a small partial to swap in (data-ajax-swap="self") or an
    // empty 204 meaning "remove this card". Forms with data-confirm show the
    // modal above before anything is submitted.
    document.addEventListener("submit", function (event) {
        var form = event.target;
        if (!(form instanceof HTMLFormElement)) return;

        var confirmMessage = form.getAttribute("data-confirm");
        if (confirmMessage && form.dataset.confirmed !== "true") {
            event.preventDefault();
            openConfirmModal(confirmMessage, function () {
                form.dataset.confirmed = "true";
                form.requestSubmit();
            });
            return;
        }

        if (!form.classList.contains("ajax-form")) return;
        event.preventDefault();

        fetch(form.action, {
            method: form.method || "POST",
            headers: { "X-Requested-With": "XMLHttpRequest" },
            body: new FormData(form),
        }).then(function (response) {
            if (!response.ok) throw new Error("request failed");
            if (form.dataset.ajaxSwap === "self") {
                return response.text().then(function (html) {
                    var wrapper = document.createElement("div");
                    wrapper.innerHTML = html.trim();
                    var node = wrapper.firstElementChild;
                    if (node) form.replaceWith(node);
                });
            }
            var card = form.closest(".item-card");
            if (card) {
                card.classList.add("is-removing");
                setTimeout(function () { card.remove(); }, 200);
            }
        }).catch(function () {
            window.vaultShowToast("Something went wrong. Please try again.", "error");
        });
    });
})();
