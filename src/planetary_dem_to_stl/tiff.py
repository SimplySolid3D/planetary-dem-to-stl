"""A tiny reader for uncompressed, single-band, strip-organised GeoTIFFs.

It reads only the bytes it needs: the header, the strip offset table, and for
each wanted image row the slice of columns inside the box. It works on a local
path or an http(s) URL (via HTTP range requests), needs nothing beyond the
standard library and numpy, and refuses any file it does not fully understand.
"""

from __future__ import annotations

import http.client
import os
import struct
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np

USER_AGENT = "planetary-dem-to-stl/0.1 (+https://github.com/SimplySolid3D/planetary-dem-to-stl)"

# TIFF field types -> (struct code, size in bytes)
_TYPES = {1: ("B", 1), 3: ("H", 2), 4: ("I", 4), 16: ("Q", 8), 6: ("b", 1), 8: ("h", 2), 9: ("i", 4), 17: ("q", 8)}
_SAMPLE_DTYPES = {(1, 8): "u1", (2, 8): "i1", (1, 16): "u2", (2, 16): "i2", (1, 32): "u4", (2, 32): "i4", (3, 32): "f4", (3, 64): "f8"}


class TiffError(RuntimeError):
    pass


class _LocalSource:
    def __init__(self, path: str):
        self.path = path
        self.size = os.path.getsize(path)
        self._local = threading.local()

    def read(self, offset: int, length: int) -> bytes:
        fh = getattr(self._local, "fh", None)
        if fh is None:
            fh = self._local.fh = open(self.path, "rb")
        fh.seek(offset)
        data = fh.read(length)
        if len(data) != length:
            raise TiffError(f"short read at {offset} in {self.path}")
        return data


class _HttpSource:
    """Range reads over keep-alive HTTPS connections, one per worker thread."""

    def __init__(self, url: str, retries: int = 4, timeout: float = 60.0):
        self.retries = retries
        self.timeout = timeout
        # Follow redirects once (planetarymaps.usgs.gov -> S3) and check that
        # the server honours ranges at all.
        req = urllib.request.Request(url, headers={"Range": "bytes=0-0", "User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 206:
                raise TiffError(f"{url} does not support HTTP range requests (status {resp.status})")
            content_range = resp.headers.get("Content-Range", "")
            self.url = resp.geturl()
        self.size = int(content_range.rsplit("/", 1)[-1]) if "/" in content_range else None
        parts = urllib.parse.urlsplit(self.url)
        self._scheme, self._host = parts.scheme, parts.netloc
        self._path = parts.path + (f"?{parts.query}" if parts.query else "")
        self._local = threading.local()
        self.requests = 0
        self.bytes = 0
        self._count_lock = threading.Lock()

    def _conn(self, fresh: bool = False):
        conn = getattr(self._local, "conn", None)
        if conn is None or fresh:
            if conn is not None:
                conn.close()
            cls = http.client.HTTPSConnection if self._scheme == "https" else http.client.HTTPConnection
            conn = self._local.conn = cls(self._host, timeout=self.timeout)
        return conn

    def read(self, offset: int, length: int) -> bytes:
        headers = {"Range": f"bytes={offset}-{offset + length - 1}", "User-Agent": USER_AGENT}
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                conn = self._conn(fresh=attempt > 0)
                conn.request("GET", self._path, headers=headers)
                resp = conn.getresponse()
                data = resp.read()
                if resp.status != 206 or len(data) != length:
                    raise TiffError(f"range {offset}+{length}: HTTP {resp.status}, got {len(data)} bytes")
                with self._count_lock:
                    self.requests += 1
                    self.bytes += length
                return data
            except (OSError, http.client.HTTPException, TiffError) as exc:
                last_error = exc
                time.sleep(0.5 * (attempt + 1))
        raise TiffError(f"giving up on {self.url} after {self.retries} attempts: {last_error}")


def open_source(path_or_url: str):
    if path_or_url.startswith(("http://", "https://")):
        return _HttpSource(path_or_url)
    return _LocalSource(path_or_url)


class StripTiff:
    """Header + strip table of one TIFF/BigTIFF; reads row slices on demand."""

    def __init__(self, path_or_url: str, workers: int = 16):
        self.source = open_source(path_or_url)
        self.workers = workers
        self._parse()

    # -- header ---------------------------------------------------------
    def _parse(self) -> None:
        head = self.source.read(0, 16)
        order = {b"II": "<", b"MM": ">"}.get(head[:2])
        if order is None:
            raise TiffError("not a TIFF file")
        self._order = order
        magic = struct.unpack(order + "H", head[2:4])[0]
        if magic == 42:
            self._big = False
            ifd = struct.unpack(order + "I", head[4:8])[0]
        elif magic == 43:
            self._big = True
            ifd = struct.unpack(order + "Q", head[8:16])[0]
        else:
            raise TiffError(f"unknown TIFF magic {magic}")
        tags = self._read_ifd(ifd)

        def one(tag, default=None):
            v = tags.get(tag)
            if v is None:
                if default is None:
                    raise TiffError(f"TIFF tag {tag} missing")
                return default
            return v[0] if isinstance(v, list) and len(v) == 1 else v

        self.width = int(one(256))
        self.height = int(one(257))
        bits = int(one(258))
        compression = int(one(259, 1))
        samples = int(one(277, 1))
        fmt = int(one(339, 1))
        self.rows_per_strip = int(one(278, self.height))
        if compression != 1:
            raise TiffError(f"compressed TIFFs are not supported (compression={compression})")
        if samples != 1:  # planar config is irrelevant for one band
            raise TiffError("only single-band TIFFs are supported")
        if 322 in tags:
            raise TiffError("tiled TIFFs are not supported by this reader")
        try:
            self.dtype = np.dtype(order + _SAMPLE_DTYPES[(fmt, bits)])
        except KeyError:
            raise TiffError(f"unsupported sample format {fmt}/{bits} bits") from None
        self.strip_offsets = np.asarray(self._resolve(tags[273]), dtype=np.int64)
        expected = -(-self.height // self.rows_per_strip)
        if len(self.strip_offsets) != expected:
            raise TiffError("strip table does not match image size")

    def _read_ifd(self, offset: int) -> dict:
        o = self._order
        if self._big:
            count = struct.unpack(o + "Q", self.source.read(offset, 8))[0]
            entry, start, inline = 20, offset + 8, 8
        else:
            count = struct.unpack(o + "H", self.source.read(offset, 2))[0]
            entry, start, inline = 12, offset + 2, 4
        raw = self.source.read(start, count * entry)
        tags = {}
        for k in range(count):
            e = raw[k * entry:(k + 1) * entry]
            if self._big:
                tag, typ, n = struct.unpack(o + "HHQ", e[:12])
                value = e[12:20]
            else:
                tag, typ, n = struct.unpack(o + "HHI", e[:8])
                value = e[8:12]
            if typ not in _TYPES:
                continue  # ASCII, rationals, doubles: not needed here
            code, size = _TYPES[typ]
            if n * size <= inline:
                tags[tag] = list(struct.unpack(o + code * n, value[: n * size]))
            else:
                ptr = struct.unpack(o + ("Q" if self._big else "I"), value)[0]
                tags[tag] = ("deferred", ptr, n, code, size)
        return tags

    def _resolve(self, value):
        if isinstance(value, tuple) and value[0] == "deferred":
            _, ptr, n, code, size = value
            data = self.source.read(ptr, n * size)
            return np.frombuffer(data, dtype=self._order + {"H": "u2", "I": "u4", "Q": "u8"}.get(code, "u4"))
        return value

    # -- pixels ---------------------------------------------------------
    def _row_offset(self, row: int, col: int) -> int:
        strip, within = divmod(row, self.rows_per_strip)
        return int(self.strip_offsets[strip]) + (within * self.width + col) * self.dtype.itemsize

    def read_rows(self, rows, col_start: int, ncols: int) -> np.ndarray:
        """Return array[len(rows), ncols]; columns wrap around the image width."""
        rows = list(rows)
        if ncols > self.width:
            raise TiffError("requested more columns than the image has")
        col_start %= self.width
        spans = [(col_start, min(ncols, self.width - col_start))]
        if spans[0][1] < ncols:
            spans.append((0, ncols - spans[0][1]))
        item = self.dtype.itemsize

        def fetch(row: int) -> np.ndarray:
            if not 0 <= row < self.height:
                raise TiffError(f"row {row} outside the image")
            parts = [np.frombuffer(self.source.read(self._row_offset(row, c0), n * item), dtype=self.dtype) for c0, n in spans]
            return np.concatenate(parts) if len(parts) > 1 else parts[0]

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            out = list(pool.map(fetch, rows))
        return np.vstack(out).astype(np.float64)
