# Changelog

## v2.1 - 2026-11-07

- **Facebook Page Reels** - the roadmap item originally slated as v1.2,
  shipped on top of v2.0. Three-phase `/video_reels` upload (start ->
  binary upload to the rupload host -> finish with
  `video_state=PUBLISHED`, after polling the video's processing status).
  Trigger it with `"format": "reel"`, or simply give a Page job a single
  video: like Instagram, a lone video on a Page is a Reel. The caption
  becomes the Reel description; media may be a public URL or a local file.

## v2.0 - 2026-11-07

- **Stories, via `"format": "story"`** (exactly one media item per job):
  - **Instagram Stories** (`media_type: STORIES`, image or video). The API
    attaches no caption and no interactive stickers (link, poll, location) -
    the story is the media itself.
  - **Facebook Page Stories**: photos go through an unpublished upload and
    then `/photo_stories`; videos use the three-phase `/video_stories`
    flow (start -> binary upload to the rupload host -> finish). Page story
    media may be a public URL or a local file.
  - A story job targeting Threads is rejected with a clear error: Threads
    has no Stories product.
- Why a major version: the job schema's `format` field now selects between
  feed post, Reel, and Story - and Meta offers no native scheduling for
  Reels or Stories, which is exactly the gap MetaMux's daemon fills.

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
