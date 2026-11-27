"use strict";

importScripts("vendor/fflate/fflate.js", "zip.js");

var CACHE_PREFIX = "duckdb-coverage-report-v3-";
var basePath = new URL(self.registration.scope).pathname;
var reportPrefix = basePath + "__report__/";
var archivePrefix = basePath + "__archive__/";
var reports = new Map();
var pendingFiles = new Map();
var initializing = new Set();

function getCacheName(id) {
  return CACHE_PREFIX + basePath + id;
}

function metadataUrl(id) {
  return new URL(archivePrefix + id, self.location.origin).href;
}

function parseReportUrl(url) {
  if (!url.pathname.startsWith(reportPrefix)) {
    return null;
  }
  var value = url.pathname.slice(reportPrefix.length);
  var slash = value.indexOf("/");
  var id = value.slice(0, slash);
  if (slash === -1 || !/^[a-f0-9-]{36}$/.test(id)) {
    return null;
  }
  var path;
  try {
    path = decodeURIComponent(value.slice(slash + 1));
  } catch (error) {
    return null;
  }
  return CoverageZip.isSafePath(path) ? { id: id, path: path } : null;
}

function contentTypeFor(path) {
  var types = {
    html: "text/html; charset=utf-8",
    css: "text/css; charset=utf-8",
    js: "text/javascript; charset=utf-8",
    png: "image/png",
    svg: "image/svg+xml",
    gif: "image/gif"
  };
  return types[path.split(".").pop()] || "application/octet-stream";
}

async function getReport(id) {
  if (!reports.has(id)) {
    var load = (async function () {
      var cache = await caches.open(getCacheName(id));
      var response = await cache.match(metadataUrl(id));
      if (!response) {
        throw new Error("This report snapshot is no longer cached. Reload the report.");
      }
      return response.json();
    }());
    reports.set(id, load);
    load.catch(function () { reports.delete(id); });
  }
  return reports.get(id);
}

async function readReportFile(id, path, url) {
  var cache = await caches.open(getCacheName(id));
  var cached = await cache.match(url);
  if (cached) {
    return cached;
  }
  var key = id + "/" + path;
  if (!pendingFiles.has(key)) {
    var load = (async function () {
      var archive = await getReport(id);
      var bytes = await CoverageZip.readFile(archive, path, fflate.inflateSync);
      if (!bytes) {
        return new Response("Coverage report file not found.", { status: 404 });
      }
      var response = new Response(bytes, {
        headers: {
          "content-type": contentTypeFor(path),
          "cache-control": "no-store"
        }
      });
      await cache.put(url, response.clone());
      return response;
    }());
    pendingFiles.set(key, load);
    load.then(function () { pendingFiles.delete(key); }, function () { pendingFiles.delete(key); });
  }
  return (await pendingFiles.get(key)).clone();
}

async function initializeReport(message) {
  if (!/^[a-f0-9-]{36}$/.test(message.id) || !CoverageZip.isSafePath(message.path)) {
    throw new Error("Invalid coverage report request.");
  }
  initializing.add(message.id);
  try {
    var archive = await CoverageZip.open(message.url);
    var cache = await caches.open(getCacheName(message.id));
    await cache.put(metadataUrl(message.id), new Response(JSON.stringify(archive), {
      headers: { "content-type": "application/json" }
    }));
    reports.set(message.id, Promise.resolve(archive));
    var url = new URL(reportPrefix + message.id + "/" + message.path, self.location.origin).href;
    var response = await readReportFile(message.id, message.path, url);
    if (!response.ok) {
      throw new Error("The requested page is absent from the coverage report.");
    }
    return { size: archive.size, files: Object.keys(archive.entries).length };
  } finally {
    initializing.delete(message.id);
  }
}

async function cleanupSnapshots() {
  var prefix = CACHE_PREFIX + basePath;
  var names = (await caches.keys()).filter(function (name) { return name.startsWith(prefix); });
  var clients = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
  var active = new Set(initializing);
  clients.forEach(function (client) {
    var report = parseReportUrl(new URL(client.url));
    if (report) { active.add(report.id); }
  });
  if (!clients.some(function (client) {
    var url = new URL(client.url);
    return url.pathname.startsWith(reportPrefix) && !parseReportUrl(url);
  })) {
    await caches.delete("duckdb-coverage-report-v2-" + basePath);
  }
  await Promise.all(names.slice(0, -5).map(async function (name) {
    var id = name.slice(prefix.length);
    if (!active.has(id)) {
      await caches.delete(name);
      reports.delete(id);
    }
  }));
}

async function readLegacyFile(url) {
  var name = "duckdb-coverage-report-v2-" + basePath;
  if (await caches.has(name)) {
    var cache = await caches.open(name);
    var response = await cache.match(url);
    if (response) { return response; }
  }
  return new Response("This report is no longer cached. Reload the report.", { status: 404 });
}

function errorResponse(error) {
  var message = String(error.message || error).replace(/[&<>"]/g, function (character) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[character];
  });
  return new Response(
    "<!doctype html><meta charset=utf-8><title>Coverage report unavailable</title>" +
    "<h1>Could not load this coverage page</h1><p>" + message + "</p>" +
    '<p><a target="_top" href="' + basePath + '">Reload the current report</a></p>',
    { status: 502, headers: { "content-type": "text/html; charset=utf-8" } }
  );
}

self.addEventListener("install", function (event) {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", function (event) {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("message", function (event) {
  if (!event.data || event.data.type !== "initialize-report" || !event.ports[0]) {
    return;
  }
  var port = event.ports[0];
  event.waitUntil(
    initializeReport(event.data).then(function (result) {
      port.postMessage({ result: result });
    }, function (error) {
      port.postMessage({ error: error.message || String(error) });
    }).then(cleanupSnapshots)
  );
});

self.addEventListener("fetch", function (event) {
  var url = new URL(event.request.url);
  if (url.origin !== self.location.origin || !url.pathname.startsWith(reportPrefix)) {
    return;
  }
  var report = parseReportUrl(url);
  if (!report) {
    event.respondWith(readLegacyFile(url.href));
    return;
  }
  event.respondWith(readReportFile(report.id, report.path, url.href).catch(errorResponse));
});
