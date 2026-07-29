(function () {
    "use strict";

    var form = document.querySelector(".search-bar");
    var input = form ? form.querySelector('input[name="q"]') : null;
    if (!form || !input) return;

    var clearBtn = document.createElement("button");
    clearBtn.type = "button";
    clearBtn.className = "search-clear";
    clearBtn.setAttribute("aria-label", "Clear search");
    clearBtn.textContent = "×";
    clearBtn.hidden = !input.value;
    form.appendChild(clearBtn);

    input.addEventListener("input", function () {
        clearBtn.hidden = !input.value;
    });

    clearBtn.addEventListener("click", function () {
        input.value = "";
        clearBtn.hidden = true;
        form.submit();
    });
})();
