# Changelog

## v1.1 - 2026-11-07

- **Instagram Reels**: a single-video job now publishes as a Reel
  (`media_type: REELS`). Videos are auto-detected from the media URL
  (`.mp4` / `.mov` / `.m4v`), or forced with `"format": "reel"` for
  extension-less CDN URLs. Reels are shared to the feed by default
  (`share_to_feed`).
- **Threads video posts** (`media_type: VIDEO`).
- Instagram carousels may mix image and video children.
- Video containers get a longer processing poll (up to ~5 minutes).
- New offline adapter tests (`tests/test_adapters.py`) with a stubbed API,
  and a Reel example job (`examples/job-reel.json`).

## v1.0 - 2026-11-07

- Initial public release.
- File-based JSON queue with an approval gate (`draft` vs `approved`),
  a 60-second daemon loop, and done/failed filing.
- Facebook Page posts (text, photo by URL or local file, multi-photo),
  Instagram single images and carousels, Threads text and image posts -
  all through the official Meta Graph API and Threads API.
- Multi-account targets (`<platform>:<alias>`) from `accounts.json`,
  tokens as literals or `env:` references.
- `init` / `add` / `list` / `run` / `loop` / `check` commands, systemd unit,
  setup guide for the Meta developer app, and an end-to-end smoke test.
