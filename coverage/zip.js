(function (root) {
  "use strict";

  function isSafePath(path) {
    return typeof path === "string" && path.length > 0 &&
      !path.startsWith("/") && !path.includes("\\") && !path.includes("\0") &&
      !/^[a-zA-Z]:/.test(path) &&
      !path.split("/").some(function (part) { return !part || part === "." || part === ".."; });
  }

  function uint64(view, offset) {
    var value = view.getUint32(offset, true) + view.getUint32(offset + 4, true) * 4294967296;
    if (!Number.isSafeInteger(value)) {
      throw new Error("ZIP offset exceeds the supported size.");
    }
    return value;
  }

  async function readRange(archive, start, length) {
    if (!Number.isSafeInteger(start) || !Number.isSafeInteger(length) ||
        start < 0 || length <= 0 || start + length > archive.size) {
      throw new Error("Invalid ZIP byte range.");
    }
    var end = start + length - 1;
    var response = await fetch(archive.url, {
      headers: { Range: "bytes=" + start + "-" + end },
      redirect: "error",
      cache: "no-store"
    });
    if (response.status !== 206) {
      throw new Error("Storage returned HTTP " + response.status + ". Reload the report if its storage link expired.");
    }
    var etag = response.headers.get("etag");
    if (archive.etag && etag && etag !== archive.etag) {
      throw new Error("The stored artifact changed. Reload the report.");
    }
    var contentRange = response.headers.get("content-range");
    if (contentRange && contentRange !== "bytes " + start + "-" + end + "/" + archive.size) {
      throw new Error("Storage returned an unexpected byte range.");
    }
    var data = new Uint8Array(await response.arrayBuffer());
    if (data.length !== length) {
      throw new Error("Storage returned an incomplete ZIP byte range.");
    }
    return data;
  }

  function parseDirectory(data, count, directoryOffset) {
    var view = new DataView(data.buffer, data.byteOffset, data.byteLength);
    var entries = Object.create(null);
    var offset = 0;
    for (var i = 0; i < count; i++) {
      if (offset + 46 > data.length || view.getUint32(offset, true) !== 0x02014b50) {
        throw new Error("Invalid ZIP file directory.");
      }
      var flags = view.getUint16(offset + 8, true);
      var method = view.getUint16(offset + 10, true);
      var checksum = view.getUint32(offset + 16, true);
      var compressedSize = view.getUint32(offset + 20, true);
      var size = view.getUint32(offset + 24, true);
      var nameLength = view.getUint16(offset + 28, true);
      var extraLength = view.getUint16(offset + 30, true);
      var commentLength = view.getUint16(offset + 32, true);
      var disk = view.getUint16(offset + 34, true);
      var localOffset = view.getUint32(offset + 42, true);
      var nameStart = offset + 46;
      var extraStart = nameStart + nameLength;
      var nextOffset = extraStart + extraLength + commentLength;
      if (nextOffset > data.length || disk !== 0 || (flags & 1)) {
        throw new Error("Unsupported or invalid ZIP entry.");
      }
      if (size === 0xffffffff || compressedSize === 0xffffffff || localOffset === 0xffffffff) {
        var foundZip64 = false;
        for (var extra = extraStart; extra + 4 <= extraStart + extraLength;) {
          var extraSize = view.getUint16(extra + 2, true);
          var nextExtra = extra + 4 + extraSize;
          if (nextExtra > extraStart + extraLength) {
            throw new Error("Invalid ZIP extra field.");
          }
          if (view.getUint16(extra, true) === 1) {
            var valueOffset = extra + 4;
            if (size === 0xffffffff) {
              if (valueOffset + 8 > nextExtra) { throw new Error("Invalid ZIP64 entry."); }
              size = uint64(view, valueOffset);
              valueOffset += 8;
            }
            if (compressedSize === 0xffffffff) {
              if (valueOffset + 8 > nextExtra) { throw new Error("Invalid ZIP64 entry."); }
              compressedSize = uint64(view, valueOffset);
              valueOffset += 8;
            }
            if (localOffset === 0xffffffff) {
              if (valueOffset + 8 > nextExtra) { throw new Error("Invalid ZIP64 entry."); }
              localOffset = uint64(view, valueOffset);
            }
            foundZip64 = true;
            break;
          }
          extra = nextExtra;
        }
        if (!foundZip64) { throw new Error("Missing ZIP64 entry information."); }
      }
      var name = new TextDecoder(flags & 2048 ? "utf-8" : "windows-1252", { fatal: true })
        .decode(data.subarray(nameStart, extraStart));
      if (isSafePath(name)) {
        if (Object.prototype.hasOwnProperty.call(entries, name)) {
          throw new Error("Duplicate ZIP filename.");
        }
        if (localOffset + 30 + nameLength + compressedSize > directoryOffset) {
          throw new Error("ZIP entry lies outside the file data.");
        }
        entries[name] = {
          offset: localOffset,
          nameLength: nameLength,
          compressedSize: compressedSize,
          size: size,
          method: method,
          checksum: checksum
        };
      }
      offset = nextOffset;
    }
    if (offset !== data.length) {
      throw new Error("Unexpected data in the ZIP file directory.");
    }
    return entries;
  }

  async function open(url) {
    var response = await fetch(url, { method: "HEAD", redirect: "follow", cache: "no-store" });
    if (!response.ok) {
      throw new Error("HTTP " + response.status + " while locating the coverage artifact.");
    }
    var archive = {
      url: response.url,
      size: Number(response.headers.get("content-length")),
      etag: response.headers.get("etag"),
      entries: null
    };
    if (!Number.isSafeInteger(archive.size) || archive.size < 22 ||
        (response.headers.get("accept-ranges") || "").toLowerCase() !== "bytes") {
      throw new Error("Artifact storage does not support ZIP byte ranges.");
    }
    var tailStart = Math.max(0, archive.size - 65557);
    var tail = await readRange(archive, tailStart, archive.size - tailStart);
    var view = new DataView(tail.buffer, tail.byteOffset, tail.byteLength);
    var end = tail.length - 22;
    while (end >= 0) {
      if (view.getUint32(end, true) === 0x06054b50 &&
          end + 22 + view.getUint16(end + 20, true) === tail.length) {
        break;
      }
      end--;
    }
    if (end < 0 || view.getUint16(end + 4, true) !== 0 || view.getUint16(end + 6, true) !== 0 ||
        view.getUint16(end + 8, true) !== view.getUint16(end + 10, true)) {
      throw new Error("Invalid or multi-volume ZIP archive.");
    }
    var count = view.getUint16(end + 10, true);
    var directorySize = view.getUint32(end + 12, true);
    var directoryOffset = view.getUint32(end + 16, true);
    if (count === 65535 || directorySize === 0xffffffff || directoryOffset === 0xffffffff) {
      var locator = end - 20;
      if (locator < 0 || view.getUint32(locator, true) !== 0x07064b50 ||
          view.getUint32(locator + 4, true) !== 0 || view.getUint32(locator + 16, true) !== 1) {
        throw new Error("Invalid ZIP64 locator.");
      }
      var zip64 = await readRange(archive, uint64(view, locator + 8), 56);
      var zip64View = new DataView(zip64.buffer, zip64.byteOffset, zip64.byteLength);
      if (zip64View.getUint32(0, true) !== 0x06064b50 ||
          zip64View.getUint32(16, true) !== 0 || zip64View.getUint32(20, true) !== 0 ||
          uint64(zip64View, 24) !== uint64(zip64View, 32)) {
        throw new Error("Invalid ZIP64 directory.");
      }
      count = uint64(zip64View, 32);
      directorySize = uint64(zip64View, 40);
      directoryOffset = uint64(zip64View, 48);
    }
    if (directoryOffset + directorySize > tailStart + end || directorySize <= 0) {
      throw new Error("Invalid ZIP directory offset.");
    }
    var directory = directoryOffset >= tailStart
      ? tail.subarray(directoryOffset - tailStart, directoryOffset - tailStart + directorySize)
      : await readRange(archive, directoryOffset, directorySize);
    archive.entries = parseDirectory(directory, count, directoryOffset);
    if (!Object.prototype.hasOwnProperty.call(archive.entries, "index.html")) {
      throw new Error("The artifact does not contain index.html at the ZIP root.");
    }
    return archive;
  }

  var crcTable = new Uint32Array(256);
  for (var i = 0; i < 256; i++) {
    var crc = i;
    for (var bit = 0; bit < 8; bit++) {
      crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
    }
    crcTable[i] = crc;
  }

  function checksum(data) {
    var crc = 0xffffffff;
    for (var i = 0; i < data.length; i++) {
      crc = (crc >>> 8) ^ crcTable[(crc ^ data[i]) & 255];
    }
    return (crc ^ 0xffffffff) >>> 0;
  }

  async function readFile(archive, path, inflate) {
    if (!isSafePath(path) || !Object.prototype.hasOwnProperty.call(archive.entries, path)) {
      return null;
    }
    var entry = archive.entries[path];
    var length = 30 + entry.nameLength + entry.compressedSize;
    var data = await readRange(archive, entry.offset, length);
    var view = new DataView(data.buffer, data.byteOffset, data.byteLength);
    if (view.getUint32(0, true) !== 0x04034b50 || (view.getUint16(6, true) & 1) ||
        view.getUint16(8, true) !== entry.method || view.getUint16(26, true) !== entry.nameLength) {
      throw new Error("Invalid ZIP local file header.");
    }
    var extraLength = view.getUint16(28, true);
    if (extraLength) {
      var remaining = await readRange(archive, entry.offset + length, extraLength);
      var complete = new Uint8Array(data.length + remaining.length);
      complete.set(data);
      complete.set(remaining, data.length);
      data = complete;
    }
    var compressed = data.subarray(30 + entry.nameLength + extraLength);
    var result;
    if (entry.method === 0) {
      result = compressed;
    } else if (entry.method === 8) {
      result = inflate(compressed, { out: new Uint8Array(entry.size) });
    } else {
      throw new Error("Unsupported ZIP compression method.");
    }
    if (result.length !== entry.size || checksum(result) !== entry.checksum) {
      throw new Error("ZIP file checksum or size does not match.");
    }
    return result;
  }

  var api = { open: open, readFile: readFile, isSafePath: isSafePath };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.CoverageZip = api;
  }
}(typeof self !== "undefined" ? self : globalThis));
