"use strict";

const assert = require("node:assert/strict");
const { test } = require("node:test");
const { zipSync, strToU8, strFromU8, inflateSync } = require("../vendor/fflate/fflate.js");
const CoverageZip = require("../zip.js");

const latestUrl = "https://artifacts.example/latest.zip";
const storageUrl = "https://storage.example/snapshot.zip?signature=one";

function fixture(options = {}) {
  const files = {
    "index.html": strToU8("<h1>Coverage</h1>"),
    "gcov.css": strToU8("body { color: black; }"),
    "src/space ü.cpp.gcov.html": strToU8("source line\n".repeat(1000)),
    "../unsafe.html": strToU8("unsafe"),
    "empty": new Uint8Array()
  };
  const data = zipSync(files, { level: options.level ?? 6 });
  if (options.comment) {
    const comment = strToU8(options.comment);
    const complete = new Uint8Array(data.length + comment.length);
    complete.set(data);
    complete.set(comment, data.length);
    new DataView(complete.buffer).setUint16(data.length - 2, comment.length, true);
    return { data: complete, files };
  }
  return { data, files };
}

function storage(t, data) {
  const originalFetch = global.fetch;
  const state = { requests: [], etag: '"snapshot-one"', status: 206, corrupt: false };
  global.fetch = async function (url, options) {
    state.requests.push({ url, options });
    if (options.method === "HEAD") {
      assert.equal(url, latestUrl);
      const response = new Response(null, {
        headers: { "content-length": data.length, "accept-ranges": "bytes", etag: state.etag }
      });
      Object.defineProperty(response, "url", { value: storageUrl });
      return response;
    }
    assert.equal(url, storageUrl, "Ranges must use the resolved storage URL");
    assert.equal(options.redirect, "error", "Later redirects must not select a newer artifact");
    const match = /^bytes=(\d+)-(\d+)$/.exec(options.headers.Range);
    assert.ok(match);
    const start = Number(match[1]);
    const end = Number(match[2]);
    assert.ok(end < data.length);
    const bytes = data.slice(start, end + 1);
    if (state.corrupt) { bytes[bytes.length - 1] ^= 1; }
    return new Response(bytes, {
      status: state.status,
      headers: {
        "content-range": `bytes ${start}-${end}/${data.length}`,
        etag: state.etag
      }
    });
  };
  t.after(() => { global.fetch = originalFetch; });
  return state;
}

test("indexes a ZIP without decompressing entries and reads only the requested file", async t => {
  const { data, files } = fixture();
  const state = storage(t, data);
  const archive = await CoverageZip.open(latestUrl);
  assert.equal(archive.url, storageUrl);
  assert.equal(state.requests.length, 2);
  assert.equal(Object.keys(archive.entries).length, 4);
  assert.ok(!Object.hasOwn(archive.entries, "../unsafe.html"));
  const result = await CoverageZip.readFile(archive, "src/space ü.cpp.gcov.html", inflateSync);
  assert.deepEqual(result, files["src/space ü.cpp.gcov.html"]);
  assert.equal(state.requests.length, 3);
  const match = state.requests[2].options.headers.Range.match(/\d+/g).map(Number);
  assert.ok(match[1] - match[0] + 1 < data.length);
  assert.equal(state.requests.filter(request => request.options.method === "HEAD").length, 1);
});

test("reads stored entries, empty entries, and an archive comment", async t => {
  const { data } = fixture({ level: 0, comment: "A comment containing PK\u0005\u0006" });
  storage(t, data);
  const archive = await CoverageZip.open(latestUrl);
  assert.equal(strFromU8(await CoverageZip.readFile(archive, "index.html", inflateSync)), "<h1>Coverage</h1>");
  assert.equal((await CoverageZip.readFile(archive, "empty", inflateSync)).length, 0);
});

test("a missing or unsafe filename does not fetch any bytes", async t => {
  const { data } = fixture();
  const state = storage(t, data);
  const archive = await CoverageZip.open(latestUrl);
  const before = state.requests.length;
  for (const path of ["absent.html", "../unsafe.html", "/index.html", "src\\file", "src/./file", "C:/file"]) {
    assert.equal(await CoverageZip.readFile(archive, path, inflateSync), null);
  }
  assert.equal(state.requests.length, before);
});

test("rejects a changed artifact validator instead of combining versions", async t => {
  const { data } = fixture();
  const state = storage(t, data);
  const archive = await CoverageZip.open(latestUrl);
  state.etag = '"snapshot-two"';
  await assert.rejects(CoverageZip.readFile(archive, "index.html", inflateSync), /artifact changed/);
});

test("an expired storage link fails without resolving the latest artifact again", async t => {
  const { data } = fixture();
  const state = storage(t, data);
  const archive = await CoverageZip.open(latestUrl);
  state.status = 403;
  await assert.rejects(CoverageZip.readFile(archive, "index.html", inflateSync), /HTTP 403.*Reload/);
  assert.equal(state.requests.filter(request => request.options.method === "HEAD").length, 1);
});

test("rejects a full response to a range request", async t => {
  const { data } = fixture();
  const state = storage(t, data);
  state.status = 200;
  await assert.rejects(CoverageZip.open(latestUrl), /HTTP 200/);
});

test("rejects corrupt entry contents", async t => {
  const { data } = fixture({ level: 0 });
  const state = storage(t, data);
  const archive = await CoverageZip.open(latestUrl);
  state.corrupt = true;
  await assert.rejects(CoverageZip.readFile(archive, "index.html", inflateSync), /checksum/);
});

test("rejects a truncated central directory", async t => {
  const { data } = fixture();
  const view = new DataView(data.buffer);
  view.setUint16(data.length - 12, 20, true);
  view.setUint16(data.length - 14, 20, true);
  storage(t, data);
  await assert.rejects(CoverageZip.open(latestUrl), /directory/);
});

test("rejects an entry extending beyond the archive", async t => {
  const { data } = fixture();
  const view = new DataView(data.buffer);
  const directory = view.getUint32(data.length - 6, true);
  view.setUint32(directory + 20, data.length, true);
  storage(t, data);
  await assert.rejects(CoverageZip.open(latestUrl), /outside/);
});

test("reads a ZIP64 central directory", async t => {
  const { data } = fixture();
  const original = new DataView(data.buffer);
  const end = data.length - 22;
  const complete = new Uint8Array(data.length + 76);
  complete.set(data.subarray(0, end));
  complete.set(data.subarray(end), end + 76);
  const view = new DataView(complete.buffer);
  view.setUint32(end, 0x06064b50, true);
  view.setBigUint64(end + 4, 44n, true);
  view.setUint16(end + 12, 45, true);
  view.setUint16(end + 14, 45, true);
  const count = BigInt(original.getUint16(end + 10, true));
  view.setBigUint64(end + 24, count, true);
  view.setBigUint64(end + 32, count, true);
  view.setBigUint64(end + 40, BigInt(original.getUint32(end + 12, true)), true);
  view.setBigUint64(end + 48, BigInt(original.getUint32(end + 16, true)), true);
  view.setUint32(end + 56, 0x07064b50, true);
  view.setBigUint64(end + 64, BigInt(end), true);
  view.setUint32(end + 72, 1, true);
  view.setUint16(end + 76 + 8, 65535, true);
  view.setUint16(end + 76 + 10, 65535, true);
  view.setUint32(end + 76 + 12, 0xffffffff, true);
  view.setUint32(end + 76 + 16, 0xffffffff, true);
  storage(t, complete);
  const archive = await CoverageZip.open(latestUrl);
  assert.equal(strFromU8(await CoverageZip.readFile(archive, "index.html", inflateSync)), "<h1>Coverage</h1>");
});

test("reads local extra fields without including them in the compressed data", async t => {
  const { data } = fixture();
  const original = new DataView(data.buffer);
  const directory = original.getUint32(data.length - 6, true);
  const insertion = 30 + original.getUint16(26, true);
  const extra = new Uint8Array([0xfe, 0xca, 0, 0]);
  const complete = new Uint8Array(data.length + extra.length);
  complete.set(data.subarray(0, insertion));
  complete.set(extra, insertion);
  complete.set(data.subarray(insertion), insertion + extra.length);
  const view = new DataView(complete.buffer);
  view.setUint16(28, extra.length, true);
  let offset = directory + extra.length;
  while (view.getUint32(offset, true) === 0x02014b50) {
    const localOffset = view.getUint32(offset + 42, true);
    if (localOffset > 0) { view.setUint32(offset + 42, localOffset + extra.length, true); }
    offset += 46 + view.getUint16(offset + 28, true) + view.getUint16(offset + 30, true) + view.getUint16(offset + 32, true);
  }
  view.setUint32(complete.length - 6, directory + extra.length, true);
  const state = storage(t, complete);
  const archive = await CoverageZip.open(latestUrl);
  const before = state.requests.length;
  assert.equal(strFromU8(await CoverageZip.readFile(archive, "index.html", inflateSync)), "<h1>Coverage</h1>");
  assert.equal(state.requests.length, before + 2);
});
