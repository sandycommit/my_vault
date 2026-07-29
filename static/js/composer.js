(function () {
    "use strict";

    var textarea = document.getElementById("composer-textarea");
    var form = document.getElementById("composer-form");
    if (!textarea || !form) return;

    function autoResize() {
        textarea.style.height = "auto";
        textarea.style.height = Math.min(textarea.scrollHeight, 200) + "px";
    }
    textarea.addEventListener("input", autoResize);
    autoResize();

    textarea.addEventListener("keydown", function (event) {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            form.requestSubmit();
        }
    });

    form.addEventListener("submit", function (event) {
        event.preventDefault();
        var text = textarea.value;
        if (!text.trim()) return;

        fetch(form.action, {
            method: "POST",
            headers: { "X-Requested-With": "XMLHttpRequest" },
            body: new FormData(form),
        }).then(function (response) {
            if (!response.ok) {
                return response.text().then(function () {
                    // Keep the text in the textarea so nothing is lost on failure.
                    window.vaultShowToast("Couldn't save that note.", "error");
                });
            }
            return response.text().then(function (html) {
                window.vaultAppendItem(html);
                textarea.value = "";
                autoResize();
                window.vaultShowToast("Saved.", "success");
            });
        }).catch(function () {
            window.vaultShowToast("Couldn't save — check your connection.", "error");
        });
    });
})();
