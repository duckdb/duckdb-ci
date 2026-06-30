"use strict";

var CACHE_NAME = "duckdb-coverage-report-v1";

self.addEventListener("install", function (event) {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", function (event) {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", function (event) {
  var url = new URL(event.request.url);

  if (!url.pathname.includes("/__report__/")) {
    return;
  }

  event.respondWith(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.match(event.request).then(function (response) {
        if (response) {
          return response;
        }
        return new Response("Coverage report file not found.", {
          status: 404,
          headers: {
            "content-type": "text/plain; charset=utf-8"
          }
        });
      });
    })
  );
});
