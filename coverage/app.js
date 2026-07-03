(function () {
  "use strict";

  var CACHE_NAME = "duckdb-coverage-report-v1";
  var DEFAULT_NAME = "linux-release-default-tests";
  var ARTIFACT_BASE = "https://artifacts.duckdb.org/latest/";

  var statusPanel = document.getElementById("status-panel");
  var statusMessage = document.getElementById("status-message");
  var statusDetail = document.getElementById("status-detail");
  var progress = document.getElementById("progress");
  var reportFrame = document.getElementById("report-frame");
  var reportBasePath = null;
  var hashChangeFromFrame = false;

  function getBasePath() {
    return new URL(".", window.location.href).pathname;
  }

  function getReportName() {
    var params = new URLSearchParams(window.location.search);
    var name = params.get("name") || DEFAULT_NAME;
    return name.trim() || DEFAULT_NAME;
  }

  function getArtifactUrl(name) {
    return ARTIFACT_BASE + "coverage-" + encodeURIComponent(name) + ".zip";
  }

  function setStatus(message, detail, progressValue) {
    statusMessage.textContent = message;
    statusDetail.textContent = detail || "";

    if (typeof progressValue === "number") {
      progress.max = 100;
      progress.value = Math.max(0, Math.min(100, progressValue));
    } else {
      progress.removeAttribute("value");
    }
  }

  function showError(stage, error) {
    var message = error && error.message ? error.message : String(error);
    statusPanel.hidden = false;
    progress.hidden = true;
    statusMessage.textContent = "Could not load coverage report.";
    statusDetail.textContent = stage + ": " + message;
  }

  function formatBytes(bytes) {
    if (bytes < 1024) {
      return bytes + " B";
    }
    if (bytes < 1024 * 1024) {
      return (bytes / 1024).toFixed(1) + " KB";
    }
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  async function waitForController() {
    if (navigator.serviceWorker.controller) {
      return;
    }
    await new Promise(function (resolve) {
      navigator.serviceWorker.addEventListener("controllerchange", resolve, { once: true });
    });
  }

  async function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) {
      throw new Error("This browser does not support service workers.");
    }
    await navigator.serviceWorker.register("sw.js");
    await navigator.serviceWorker.ready;
    await waitForController();
  }

  async function downloadArtifact(url, name) {
    setStatus("Downloading coverage report...", "coverage-" + name + ".zip", null);

    var response = await fetch(url, { redirect: "follow" });
    if (!response.ok) {
      throw new Error("HTTP " + response.status + " while fetching " + url);
    }
    if (!response.body) {
      return new Uint8Array(await response.arrayBuffer());
    }

    var contentLength = Number(response.headers.get("content-length")) || 0;
    var reader = response.body.getReader();
    var chunks = [];
    var received = 0;

    while (true) {
      var result = await reader.read();
      if (result.done) {
        break;
      }
      chunks.push(result.value);
      received += result.value.length;

      if (contentLength) {
        setStatus(
          "Downloading coverage report...",
          formatBytes(received) + " of " + formatBytes(contentLength),
          (received / contentLength) * 100
        );
      } else {
        setStatus("Downloading coverage report...", formatBytes(received) + " downloaded", null);
      }
    }

    var bytes = new Uint8Array(received);
    var offset = 0;
    for (var i = 0; i < chunks.length; i++) {
      bytes.set(chunks[i], offset);
      offset += chunks[i].length;
    }
    return bytes;
  }

  function isSafeZipPath(path) {
    return path &&
      path[0] !== "/" &&
      !path.match(/^[a-zA-Z]:/) &&
      !path.split("/").includes("..") &&
      path[path.length - 1] !== "/";
  }

  function getHashReportPath() {
    var hash = window.location.hash || "";
    if (!hash.startsWith("#/")) {
      return {
        path: "index.html",
        fragment: ""
      };
    }

    var value = hash.slice(2);
    var fragmentIndex = value.indexOf("#");
    var path = fragmentIndex === -1 ? value : value.slice(0, fragmentIndex);
    var fragment = fragmentIndex === -1 ? "" : value.slice(fragmentIndex);

    try {
      path = decodeURI(path);
    } catch (error) {
      return {
        path: "index.html",
        fragment: ""
      };
    }

    if (!isSafeZipPath(path)) {
      return {
        path: "index.html",
        fragment: ""
      };
    }
    return {
      path: path,
      fragment: fragment
    };
  }

  function getReportUrlFromHash(basePath) {
    var target = getHashReportPath();
    return basePath + "__report__/" + target.path + target.fragment;
  }

  function getHashFromReportUrl(url, basePath) {
    if (url.origin !== window.location.origin || !url.pathname.startsWith(basePath + "__report__/")) {
      return null;
    }

    var path = url.pathname.slice((basePath + "__report__/").length);
    if (!isSafeZipPath(path)) {
      return null;
    }
    return "#/" + path + url.hash;
  }

  function navigateToHashReport() {
    if (!reportBasePath) {
      return;
    }
    var target = getReportUrlFromHash(reportBasePath);
    var current = reportFrame.contentWindow ? reportFrame.contentWindow.location.pathname + reportFrame.contentWindow.location.hash : "";
    if (current !== target) {
      reportFrame.src = target;
    }
  }

  function contentTypeFor(path) {
    if (path.endsWith(".html")) {
      return "text/html; charset=utf-8";
    }
    if (path.endsWith(".css")) {
      return "text/css; charset=utf-8";
    }
    if (path.endsWith(".js")) {
      return "text/javascript; charset=utf-8";
    }
    if (path.endsWith(".png")) {
      return "image/png";
    }
    if (path.endsWith(".svg")) {
      return "image/svg+xml";
    }
    if (path.endsWith(".gif")) {
      return "image/gif";
    }
    return "application/octet-stream";
  }

  async function cacheReport(files, basePath) {
    var names = Object.keys(files).filter(isSafeZipPath);
    if (!files["index.html"]) {
      throw new Error("The artifact does not contain index.html at the zip root.");
    }

    var cache = await caches.open(CACHE_NAME);
    var keys = await cache.keys();
    await Promise.all(keys.map(function (request) {
      return cache.delete(request);
    }));

    for (var i = 0; i < names.length; i++) {
      var name = names[i];
      var url = new URL(basePath + "__report__/" + name, window.location.origin);
      var response = new Response(files[name], {
        headers: {
          "content-type": contentTypeFor(name),
          "cache-control": "no-store"
        }
      });
      await cache.put(url.href, response);

      if (i % 100 === 0 || i === names.length - 1) {
        setStatus("Preparing coverage report...", (i + 1) + " of " + names.length + " files", ((i + 1) / names.length) * 100);
        await new Promise(function (resolve) {
          setTimeout(resolve, 0);
        });
      }
    }
  }

  async function load() {
    var name = getReportName();
    var basePath = getBasePath();
    var artifactUrl = getArtifactUrl(name);
    reportBasePath = basePath;

    try {
      await registerServiceWorker();
    } catch (error) {
      showError("Service worker registration failed", error);
      return;
    }

    var zipBytes;
    try {
      zipBytes = await downloadArtifact(artifactUrl, name);
    } catch (error) {
      showError("Download failed", error);
      return;
    }

    var files;
    try {
      setStatus("Extracting coverage report...", formatBytes(zipBytes.length) + " archive", null);
      files = window.fflate.unzipSync(zipBytes);
    } catch (error) {
      showError("Extraction failed", error);
      return;
    }

    try {
      await cacheReport(files, basePath);
    } catch (error) {
      showError("Cache write failed", error);
      return;
    }

    reportFrame.addEventListener("load", function () {
      statusPanel.hidden = true;
    }, { once: true });
    reportFrame.addEventListener("load", function () {
      var reportHash;
      try {
        reportHash = getHashFromReportUrl(new URL(reportFrame.contentWindow.location.href), basePath);
      } catch (error) {
        return;
      }

      if (reportHash && window.location.hash !== reportHash) {
        hashChangeFromFrame = true;
        window.location.hash = reportHash;
      }
    });

    window.addEventListener("hashchange", function () {
      if (hashChangeFromFrame) {
        hashChangeFromFrame = false;
        return;
      }
      navigateToHashReport();
    });

    reportFrame.src = getReportUrlFromHash(basePath);
  }

  load();
}());
