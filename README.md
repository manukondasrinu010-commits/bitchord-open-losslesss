# BitChord Open Lossless Catalogue Addon

A small HTTP addon for BitChord that searches Internet Archive audio items and returns
**only actual `.flac` files** whose item metadata declares a public-domain or supported
Creative Commons license. It does not convert MP3/AAC into FLAC and does not promise
that every result is 24-bit or hi-res.

## Requirements

- Python 3.10+ (standard library only)
- Outbound internet access to `archive.org`
- For BitChord on another device: deploy behind a public HTTPS URL

## Run locally

```bash
python server.py
```

It listens on port 8080 by default. Override with `PORT=9000 python server.py`.

## Test locally

```bash
python -m unittest -v test_addon.py
```

Then open these URLs:

- `http://127.0.0.1:8080/manifest.json`
- `http://127.0.0.1:8080/health`
- `http://127.0.0.1:8080/search?q=classical&quality=lossless`
- `http://127.0.0.1:8080/stream/PASTE_TRACK_ID_HERE?quality=lossless`

## Add to BitChord

Deploy this server to an HTTPS host that runs Python, then in BitChord go to
**Settings → Sources → Add an addon** and paste the deployed root URL or its
`/manifest.json` URL.

A local `127.0.0.1` address is only reachable on the same device and is not a public
deployment URL.

## Scope and limitations

- Source: Internet Archive, restricted to supported public-domain / Creative Commons
  license URLs and items with real FLAC files.
- This is not a commercial streaming catalogue. It will not unlock Spotify, Apple Music,
  YouTube Music, or other paid catalogues.
- Metadata can be incomplete. The addon reports FLAC codec/container but omits sample
  rate, bit depth, and bitrate unless the source can reliably provide them.
- The output gate is disabled (`checkValidLossless: 0`), so the addon can be queried on
  any output. A lossy output cannot make a lossy Bluetooth path bit-perfect.
- `allowDownloads: 1` allows BitChord to use this source for downloads. Only download
  music you are legally entitled to save.
- Internet Archive availability, licensing metadata, and direct file access may change.

## Deployment

Use a Python-capable host with HTTPS. Example command:

```bash
python server.py
```

Set the host's `PORT` environment variable if required. Ensure the hosting platform
routes public HTTPS requests to that port.
