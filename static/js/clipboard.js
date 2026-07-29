(function () {
    "use strict";

    document.addEventListener("click", function (event) {
        var button = event.target.closest(".copy-btn");
        if (!button) return;

        var targetId = button.getAttribute("data-copy-target");
        var codeEl = targetId ? document.getElementById(targetId) : null;
        if (!codeEl) return;

        navigator.clipboard.writeText(codeEl.textContent).then(function () {
            var original = button.textContent;
            button.textContent = "Copied!";
            window.vaultShowToast && window.vaultShowToast("Copied to clipboard.", "success");
            setTimeout(function () { button.textContent = original; }, 1500);
        }).catch(function () {
            window.vaultShowToast && window.vaultShowToast("Couldn't copy — select and copy manually.", "error");
        });
    });
})();
