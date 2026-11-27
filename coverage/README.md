# Coverage viewer

The viewer follows the artifact redirect once, then pins that report snapshot to
the resolved storage URL, size, and ETag. It reads the ZIP central directory with
byte ranges and fetches and decompresses individual files when they are opened.
Only ZIP metadata and requested pages and assets are written to the browser cache.

Every report view has a separate cache and URL prefix. Opening a newer artifact
in another tab does not change an existing tab's snapshot. The service worker can
recover snapshot metadata from the cache after it restarts. Cached pages remain
available when a signed storage URL expires; uncached pages show a reload link.
The viewer does not resolve a newer artifact to complete an older snapshot.

Storage must support HEAD requests and byte ranges, and expose Content-Length,
Accept-Ranges, and ETag to the browser. File sizes and CRC checksums are verified
after decompression. Stored, deflated, and ZIP64 entries are supported.

Run the ZIP reader regression tests with:

```sh
node --test coverage/tests/zip.test.js
```
