#!/usr/bin/env python3
"""BitChord lossless music addon backed by openly licensed Internet Archive audio.

Only returns tracks with a real .flac file and a recognized public-domain /
Creative Commons license. Uses Python's standard library; no pip installs needed.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import base64
import json
import os
import re
import socket
import time

PORT = int(os.environ.get("PORT", "8080"))
USER_AGENT = "BitChord-Lossless-Addon/1.0 (Internet Archive metadata search)"
CACHE_TTL = 300
_cache = {}

MANIFEST = {
    "id": "dev.sunny.bitchord.open-lossless",
    "name": "Open Lossless Catalogue",
    "version": "1.0.0",
    "resources": ["search", "stream"],
    "allowDownloads": 1,
    "checkValidLossless": 0,
    "settings": [
        {
            "key": "quality",
            "type": "select",
            "default": "lossless",
            "options": [
                {"label": "Lossless", "value": "lossless"},
                {"label": "High", "value": "high"},
                {"label": "Low", "value": "low"}
            ]
        }
    ]
}

# Licenses that permit sharing/remixing or identify public-domain material.
ALLOWED_LICENSE_MARKERS = (
    "creativecommons.org/publicdomain/zero/",
    "creativecommons.org/publicdomain/mark/",
    "creativecommons.org/licenses/by/",
    "creativecommons.org/licenses/by-sa/",
    "creativecommons.org/licenses/by/3.0/",
    "creativecommons.org/licenses/by/4.0/",
    "creativecommons.org/licenses/by-sa/3.0/",
    "creativecommons.org/licenses/by-sa/4.0/",
)

def _get_json(url, timeout=12):
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))

def _licensed(license_url):
    value = (license_url or "").strip().lower()
    return any(marker in value for marker in ALLOWED_LICENSE_MARKERS)

def _encode_track(identifier, filename):
    raw = json.dumps({"identifier": identifier, "filename": filename},
                     separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

def _decode_track(track_id):
    padded = track_id + "=" * (-len(track_id) % 4)
    obj = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    identifier = obj.get("identifier", "")
    filename = obj.get("filename", "")
    # Prevent IDs from being used to construct arbitrary external URLs.
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,200}", identifier):
        raise ValueError("Invalid archive identifier")
    if not filename or filename.startswith("/") or ".." in filename.split("/"):
        raise ValueError("Invalid archive filename")
    return identifier, filename

def _archive_results(query, rows=15):
    cache_key = query.casefold().strip()
    now = time.time()
    cached = _cache.get(cache_key)
    if cached and now - cached[0] < CACHE_TTL:
        return cached[1]

    # The public Archive.org advanced-search endpoint is used only for discovery.
    # We then inspect item metadata and only return licensed FLAC files.
    from urllib.parse import urlencode
    params = urlencode({
        "q": f'mediatype:audio AND "{query}"',
        "fl[]": ["identifier", "title", "creator", "licenseurl"],
        "rows": str(rows),
        "page": "1",
        "output": "json",
    }, doseq=True)
    result = _get_json("https://archive.org/advancedsearch.php?" + params)
    docs = result.get("response", {}).get("docs", [])
    tracks = []
    for doc in docs:
        identifier = str(doc.get("identifier", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,200}", identifier):
            continue
        try:
            metadata = _get_json("https://archive.org/metadata/" + quote(identifier, safe=""))
        except (HTTPError, URLError, TimeoutError, socket.timeout, ValueError):
            continue
        meta = metadata.get("metadata", {})
        license_url = str(meta.get("licenseurl") or doc.get("licenseurl") or "")
        if not _licensed(license_url):
            continue
        files = metadata.get("files", [])
        flac_files = [
            f for f in files
            if isinstance(f, dict)
            and str(f.get("name", "")).lower().endswith(".flac")
            and not f.get("private")
            and f.get("source") != "metadata"
        ]
        for file_info in flac_files[:3]:
            filename = str(file_info["name"])
            title = str(meta.get("title") or doc.get("title") or identifier)
            # If an item contains multiple FLAC files, use each file as a separate result.
            file_title = filename.rsplit("/", 1)[-1]
            track_title = title if len(flac_files) == 1 else f"{title} — {file_title}"
            creator = meta.get("creator") or meta.get("artist") or doc.get("creator") or "Unknown artist"
            if isinstance(creator, list):
                creator = ", ".join(str(x) for x in creator[:3])
            album = meta.get("album") or title
            token = _encode_track(identifier, filename)
            tracks.append({
                "id": token,
                "title": track_title,
                "artist": str(creator),
                "album": str(album),
                "artworkURL": f"https://archive.org/services/img/{quote(identifier, safe='')}",
                "format": "flac",
                "audioQuality": "LOSSLESS",
            })
    _cache[cache_key] = (now, tracks)
    return tracks

def handle_request(method, path, query_string=""):
    """Small testable router. Returns (status, headers, body_bytes)."""
    parsed = urlparse(path)
    params = parse_qs(query_string)
    headers = {"Content-Type": "application/json; charset=utf-8",
               "Cache-Control": "no-store"}
    def response(status, value):
        return status, headers, json.dumps(value, ensure_ascii=False).encode("utf-8")

    if method not in ("GET", "HEAD"):
        return response(405, {"error": "Method not allowed"})
    if parsed.path == "/":
        return response(200, {"service": MANIFEST["name"], "manifest": "/manifest.json"})
    if parsed.path == "/manifest.json":
        return response(200, MANIFEST)
    if parsed.path == "/health":
        return response(200, {"ok": True, "service": MANIFEST["id"]})
    if parsed.path == "/search":
        query = (params.get("q") or [""])[0].strip()
        if not query:
            return response(200, {"tracks": []})
        if len(query) > 160:
            return response(400, {"error": "Search query is too long"})
        try:
            tracks = _archive_results(query)
            return response(200, {"tracks": tracks})
        except (HTTPError, URLError, TimeoutError, socket.timeout, ValueError, KeyError) as exc:
            return response(502, {"tracks": [], "error": "Catalogue lookup failed"})
    if parsed.path.startswith("/stream/"):
        track_id = parsed.path[len("/stream/"):]
        try:
            identifier, filename = _decode_track(track_id)
        except Exception:
            return response(404, {"error": "Track not found"})
        try:
            metadata = _get_json("https://archive.org/metadata/" + quote(identifier, safe=""))
        except (HTTPError, URLError, TimeoutError, socket.timeout, ValueError):
            return response(502, {"error": "Could not resolve archive item"})
        meta = metadata.get("metadata", {})
        if not _licensed(str(meta.get("licenseurl") or "")):
            return response(404, {"error": "Track is not in the supported license catalogue"})
        found = any(
            isinstance(f, dict) and f.get("name") == filename
            and str(f.get("name", "")).lower().endswith(".flac")
            and not f.get("private")
            for f in metadata.get("files", [])
        )
        if not found:
            return response(404, {"error": "FLAC file not found"})
        media_url = "https://archive.org/download/" + quote(identifier, safe="") + "/" + quote(filename, safe="/")
        return response(200, {
            "url": media_url,
            "format": "flac",
            "quality": "Lossless FLAC",
            "codec": "flac",
            "container": "flac",
            "manifest": "none",
            "encrypted": False
        })
    return response(404, {"error": "Not found"})

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._respond("GET")
    def do_HEAD(self):
        self._respond("HEAD")
    def _respond(self, method):
        status, headers, body = handle_request(method, self.path.split("?", 1)[0],
                                               self.path.split("?", 1)[1] if "?" in self.path else "")
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if method != "HEAD":
            self.wfile.write(body)
    def log_message(self, fmt, *args):
        # Avoid logging full query strings or potentially sensitive values.
        print("%s - %s" % (self.address_string(), args[0] if args else "request"))

if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"{MANIFEST['name']} listening on 0.0.0.0:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
