(function () {
  "use strict";

  var DEFAULT_NAME = "linux-release-default-tests";
  var DEFAULT_REPORT_TITLE = "LCOV - code coverage report";
  var ARTIFACT_BASE = "https://artifacts.duckdb.org/";

  var statusPanel = document.getElementById("status-panel");
  var statusMessage = document.getElementById("status-message");
  var statusDetail = document.getElementById("status-detail");
  var progress = document.getElementById("progress");
  var reportFrame = document.getElementById("report-frame");
  var reportBasePath = null;
  var reportId = null;
  var hashChangeFromFrame = false;

  function getBasePath() {
    return new URL(".", window.location.href).pathname;
  }

  function getBranch(basePath) {
    var parts = basePath.split("/").filter(Boolean);
    return decodeURIComponent(parts[parts.length - 1]);
  }

  function getReportName() {
    var params = new URLSearchParams(window.location.search);
    var name = params.get("name") || DEFAULT_NAME;
    return name.trim() || DEFAULT_NAME;
  }

  function getArtifactUrl(branch, name) {
    return ARTIFACT_BASE + encodeURIComponent(branch) + "/coverage-" + encodeURIComponent(name) + ".zip";
  }

  function updateReportTitle(branch) {
    var reportDocument = reportFrame.contentDocument;
    if (!reportDocument) {
      return;
    }

    var title = reportDocument.querySelector("td.title");
    if (!title || title.textContent.trim() !== DEFAULT_REPORT_TITLE) {
      return;
    }

    var branchName = reportDocument.createElement("strong");
    branchName.textContent = branch;
    title.textContent = "Code coverage of ";
    title.appendChild(branchName);
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

  async function waitForController() {
    if (navigator.serviceWorker.controller) {
      return;
    }
    await new Promise(function (resolve) {
      navigator.serviceWorker.addEventListener("controllerchange", resolve, { once: true });
    });
  }

  async function registerServiceWorker(basePath) {
    if (!("serviceWorker" in navigator)) {
      throw new Error("This browser does not support service workers.");
    }

    var expectedScriptUrl = new URL(basePath + "sw.js", window.location.origin).href;
    var controller = navigator.serviceWorker.controller;
    if (controller && controller.scriptURL !== expectedScriptUrl) {
      var legacyRegistration = await navigator.serviceWorker.getRegistration();
      if (legacyRegistration) {
        await legacyRegistration.unregister();
      }
      window.location.reload();
      return false;
    }

    var registration = await navigator.serviceWorker.register("sw.js", { updateViaCache: "none" });
    await registration.update();
    var installing = registration.installing;
    if (installing && installing.state !== "activated") {
      await new Promise(function (resolve, reject) {
        installing.addEventListener("statechange", function () {
          if (installing.state === "activated") { resolve(); }
          if (installing.state === "redundant") { reject(new Error("Service worker installation failed.")); }
        });
      });
    }
    await navigator.serviceWorker.ready;
    await waitForController();
    return true;
  }

  async function prepareReport(url, id, path) {
    return new Promise(function (resolve, reject) {
      var channel = new MessageChannel();
      var timeout = setTimeout(function () {
        channel.port1.close();
        reject(new Error("Timed out while preparing the report. Reload to retry."));
      }, 60000);
      channel.port1.onmessage = function (event) {
        clearTimeout(timeout);
        channel.port1.close();
        if (event.data.error) {
          reject(new Error(event.data.error));
        } else {
          resolve(event.data.result);
        }
      };
      navigator.serviceWorker.controller.postMessage({
        type: "initialize-report",
        url: url,
        id: id,
        path: path
      }, [channel.port2]);
    });
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
    return basePath + "__report__/" + reportId + "/" + target.path + target.fragment;
  }

  function getHashFromReportUrl(url, basePath) {
    var prefix = basePath + "__report__/" + reportId + "/";
    if (url.origin !== window.location.origin || !url.pathname.startsWith(prefix)) {
      return null;
    }

    var path = url.pathname.slice(prefix.length);
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

  async function load() {
    var name = getReportName();
    var basePath = getBasePath();
    var branch = getBranch(basePath);
    var artifactUrl = getArtifactUrl(branch, name);
    document.title = "Code coverage of " + branch;
    reportBasePath = basePath;

    try {
      if (!await registerServiceWorker(basePath)) {
        return;
      }
    } catch (error) {
      showError("Service worker registration failed", error);
      return;
    }

    reportId = crypto.randomUUID();
    try {
      setStatus("Opening coverage report...", "coverage-" + name + ".zip", null);
      var report = await prepareReport(artifactUrl, reportId, getHashReportPath().path);
      setStatus("Loading coverage page...", report.files + " files available on demand", null);
    } catch (error) {
      showError("Report preparation failed", error);
      return;
    }

    reportFrame.addEventListener("load", function () {
      statusPanel.hidden = true;
    }, { once: true });
    reportFrame.addEventListener("load", function () {
      var reportHash;
      try {
        updateReportTitle(branch);
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
