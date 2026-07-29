(function () {
    "use strict";

    var feed = document.getElementById("item-feed");
    if (!feed) return;

    var loading = false;

    function loadMore() {
        if (loading || feed.dataset.hasMore !== "true") return;

        var baseUrl = feed.dataset.loadMoreUrl;
        var oldestId = feed.dataset.oldestId;
        if (!baseUrl) return;

        loading = true;
        var url = baseUrl + (oldestId ? "?before=" + encodeURIComponent(oldestId) : "");

        fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } })
            .then(function (response) {
                feed.dataset.hasMore = response.headers.get("X-Has-More") || "false";
                var newOldestId = response.headers.get("X-Oldest-Id");
                if (newOldestId) feed.dataset.oldestId = newOldestId;
                return response.text();
            })
            .then(function (html) {
                if (!html.trim()) return;
                var previousHeight = feed.scrollHeight;
                var wrapper = document.createElement("div");
                wrapper.innerHTML = html;
                while (wrapper.firstChild) {
                    feed.insertBefore(wrapper.firstChild, feed.firstChild);
                }
                feed.scrollTop = feed.scrollHeight - previousHeight;
            })
            .finally(function () { loading = false; });
    }

    feed.addEventListener("scroll", function () {
        if (feed.scrollTop < 80) loadMore();
    });
})();
