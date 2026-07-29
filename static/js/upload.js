(function () {
    "use strict";

    var uploadForm = document.getElementById("upload-form");
    var fileInput = document.getElementById("upload-input");
    var dropZone = document.querySelector(".app-main");
    if (!uploadForm || !fileInput) return;

    function uploadFile(file) {
        var formData = new FormData();
        formData.append("file", file);
        var csrfInput = uploadForm.querySelector("input[name=csrfmiddlewaretoken]");
        formData.append("csrfmiddlewaretoken", csrfInput.value);

        window.vaultShowToast("Uploading " + file.name + "…", "info");

        fetch(uploadForm.action, {
            method: "POST",
            headers: { "X-Requested-With": "XMLHttpRequest" },
            body: formData,
        }).then(function (response) {
            if (!response.ok) {
                return response.text().then(function (errorText) {
                    window.vaultShowToast(errorText || "Upload failed.", "error");
                });
            }
            return response.text().then(function (html) {
                window.vaultAppendItem(html);
                window.vaultShowToast("Uploaded.", "success");
            });
        }).catch(function () {
            window.vaultShowToast("Upload failed — check your connection.", "error");
        });
    }

    fileInput.addEventListener("change", function () {
        if (fileInput.files.length) {
            uploadFile(fileInput.files[0]);
            fileInput.value = "";
        }
    });

    if (dropZone) {
        ["dragenter", "dragover"].forEach(function (eventName) {
            dropZone.addEventListener(eventName, function (event) {
                event.preventDefault();
                dropZone.classList.add("is-drag-over");
            });
        });
        ["dragleave", "drop"].forEach(function (eventName) {
            dropZone.addEventListener(eventName, function (event) {
                event.preventDefault();
                dropZone.classList.remove("is-drag-over");
            });
        });
        dropZone.addEventListener("drop", function (event) {
            var files = event.dataTransfer ? event.dataTransfer.files : [];
            for (var i = 0; i < files.length; i++) {
                uploadFile(files[i]);
            }
        });
    }
})();
