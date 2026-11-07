#!/usr/bin/env python3
"""Offline adapter tests for MetaMux - no network, no tokens needed.

The Graph / Threads API functions are replaced with recording stubs, and the
tests assert that each job shape produces the right API calls:
  - IG image          -> image container, no media_type
  - IG video URL      -> REELS container with video_url (auto-detected)
  - IG format="reel"  -> REELS container even for extension-less URLs
  - IG carousel       -> child containers + CAROUSEL parent (video child ok)
  - IG local file     -> rejected with JobError before any API call
  - Threads text      -> TEXT container
  - Threads video     -> VIDEO container with video_url

Run: python3 tests/test_adapters.py
"""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location(
    "metamux", os.path.join(ROOT, "metamux.py"))
mm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mm)

ACCOUNT = {"page_id": "111", "ig_business_id": "222", "threads_user_id": "333",
           "graph_token": "stub-graph-token", "threads_token": "stub-threads"}
mm.get_account = lambda alias: ACCOUNT

CALLS = []


def fake_graph(path, token, params=None, method="POST"):
    CALLS.append(("graph", method, path, dict(params or {})))
    if method == "GET":
        return {"status_code": "FINISHED"}
    if path.endswith("/media_publish"):
        return {"id": "ig-published"}
    return {"id": "ig-container"}


def fake_threads(path, token, params=None, method="POST"):
    CALLS.append(("threads", method, path, dict(params or {})))
    if method == "GET":
        return {"status": "FINISHED"}
    if path.endswith("/threads_publish"):
        return {"id": "threads-published"}
    return {"id": "threads-container"}


mm.graph = fake_graph
mm.threads_api = fake_threads


def job(**kw):
    base = {"id": "t", "caption": "hello", "media": [], "targets": [],
            "publish_at": "2026-01-01T00:00:00+00:00", "status": "approved",
            "attempts": 0}
    base.update(kw)
    return base


def creates(api):
    return [c for c in CALLS if c[0] == api and c[1] == "POST"
            and (c[2].endswith("/media") or c[2].endswith("/threads"))]


def check(name, cond):
    if not cond:
        raise AssertionError("FAILED: " + name)
    print("ok -", name)


def main():
    # IG single image
    CALLS.clear()
    out = mm.publish_ig(job(media=["https://x.test/a.jpg"]), "main")
    c = creates("graph")
    check("ig image publishes", out == "ig-published")
    check("ig image uses image_url, no media_type",
          c[0][3].get("image_url") == "https://x.test/a.jpg"
          and "media_type" not in c[0][3])

    # IG video auto-detected as Reel
    CALLS.clear()
    mm.publish_ig(job(media=["https://x.test/clip.mp4"]), "main")
    c = creates("graph")
    check("ig .mp4 auto-detected as REELS",
          c[0][3].get("media_type") == "REELS"
          and c[0][3].get("video_url") == "https://x.test/clip.mp4")

    # IG Reel forced by format, extension-less URL
    CALLS.clear()
    mm.publish_ig(job(media=["https://cdn.test/media/abc"],
                      format="reel"), "main")
    c = creates("graph")
    check("ig format=reel forces REELS",
          c[0][3].get("media_type") == "REELS"
          and c[0][3].get("video_url") == "https://cdn.test/media/abc")

    # IG carousel with a video child
    CALLS.clear()
    mm.publish_ig(job(media=["https://x.test/a.jpg",
                             "https://x.test/b.mov"]), "main")
    c = creates("graph")
    check("ig carousel parent is CAROUSEL",
          any(p.get("media_type") == "CAROUSEL" for _, _, _, p in c))
    check("ig carousel video child uses video_url",
          any(p.get("video_url") == "https://x.test/b.mov"
              and p.get("is_carousel_item") == "true" for _, _, _, p in c))

    # IG local file rejected before any call
    CALLS.clear()
    try:
        mm.publish_ig(job(media=["/tmp/local.jpg"]), "main")
        raise SystemExit("ig local file was NOT rejected")
    except mm.JobError:
        check("ig local file rejected with JobError", True)
    check("ig local file made no API calls", len(CALLS) == 0)

    # Threads text
    CALLS.clear()
    out = mm.publish_threads(job(media=[]), "main")
    c = creates("threads")
    check("threads text publishes", out == "threads-published")
    check("threads text uses media_type TEXT",
          c[0][3].get("media_type") == "TEXT")

    # Threads video
    CALLS.clear()
    mm.publish_threads(job(media=["https://x.test/v.mp4"]), "main")
    c = creates("threads")
    check("threads video uses media_type VIDEO + video_url",
          c[0][3].get("media_type") == "VIDEO"
          and c[0][3].get("video_url") == "https://x.test/v.mp4")

    # Threads image stays IMAGE
    CALLS.clear()
    mm.publish_threads(job(media=["https://x.test/p.png"]), "main")
    c = creates("threads")
    check("threads image stays IMAGE",
          c[0][3].get("media_type") == "IMAGE")

    print("ALL ADAPTER TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
