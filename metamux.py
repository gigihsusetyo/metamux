#!/usr/bin/env python3
"""MetaMux 1.1 - a tiny, dependency-free, multi-account scheduler for Meta platforms.

v1.1 adds Instagram Reels and Threads video posts: a single video job is
published as a Reel on Instagram (auto-detected from the media URL, or forced
with "format": "reel" in the job), and as a video post on Threads.

One JSON file per job, one folder-based queue, one daemon. MetaMux publishes
to Facebook Pages, Instagram and Threads through the *official* Meta Graph API
and Threads API - no browser automation, no unofficial endpoints.

Commands:
  init             create folders + a starter accounts.json from the example
  add <job.json>   enqueue a job file into queue/
  list             show the queue
  run              process the queue once
  loop             daemon mode: process the queue every 60 seconds
  check            verify every configured account token (no secrets printed)

The runner only executes jobs whose status is "approved" and whose
publish_at is due. Jobs with status "draft" are never touched - that gate is
the whole point: a human (or an AI orchestrator) proposes, a human approves,
the daemon publishes.

Targets are "<platform>:<account-alias>", e.g. "page:main", "ig:main",
"threads:main", where the alias is a key in accounts.json. One job can fan
out to several targets and several accounts at once - that's the mux.
"""
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
QUEUE = os.path.join(BASE, "queue")
DONE = os.path.join(BASE, "done")
FAILED = os.path.join(BASE, "failed")
LOGS = os.path.join(BASE, "logs")
PUBLISH_LOG = os.path.join(LOGS, "publish.log")
CONFIG = os.path.join(BASE, "accounts.json")
CONFIG_EXAMPLE = os.path.join(BASE, "accounts.example.json")

GRAPH_API = "https://graph.facebook.com/v21.0"
THREADS_API = "https://graph.threads.net/v1.0"
MAX_ATTEMPTS = 2
TRANSIENT_BACKOFF_MIN = 15
RATE_LIMIT_CODES = {4, 17, 32, 613, 80004, 80005, 80006}


class JobError(Exception):
    """A normal job failure (counts toward attempts)."""


class TransientError(JobError):
    """Rate limit / temporary platform error: back off, don't count attempts."""


class ConfigError(JobError):
    """accounts.json is missing or incomplete."""


# ------------------------------------------------------------------ config

def resolve_secret(value):
    """A config value is either a literal or 'env:VAR_NAME'."""
    if isinstance(value, str) and value.startswith("env:"):
        return os.environ.get(value[4:], "")
    return value or ""


def load_accounts():
    if not os.path.exists(CONFIG):
        raise ConfigError(
            "accounts.json not found - run `python3 metamux.py init` first")
    with open(CONFIG, encoding="utf-8") as f:
        data = json.load(f)
    accounts = data.get("accounts")
    if not isinstance(accounts, dict) or not accounts:
        raise ConfigError("accounts.json: 'accounts' must be a non-empty object")
    return accounts


def get_account(alias):
    accounts = load_accounts()
    acc = accounts.get(alias)
    if acc is None:
        raise ConfigError(f"unknown account alias: {alias!r} "
                          f"(configured: {', '.join(sorted(accounts))})")
    return acc


def account_token(acc, *fields):
    for field in fields:
        token = resolve_secret(acc.get(field, ""))
        if token:
            return token
    raise ConfigError(f"account is missing a token (tried: {', '.join(fields)})")


# ------------------------------------------------------------------ http

def _api_call(base, path, token, params=None, method="POST"):
    url = f"{base}/{path.lstrip('/')}"
    data = dict(params or {})
    data["access_token"] = token
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body if method == "POST" else None,
                                 method=method)
    if method == "GET":
        url = url + "?" + urllib.parse.urlencode(data)
        req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode("utf-8"))
        except Exception:
            raise JobError(f"HTTP {e.code} calling {path}")
    except urllib.error.URLError as e:
        raise TransientError(f"network error calling {path}: {e.reason}")
    err = payload.get("error") if isinstance(payload, dict) else None
    if err:
        code = err.get("code")
        msg = err.get("message", "unknown API error")
        if code in RATE_LIMIT_CODES:
            raise TransientError(f"rate limited on {path} (code {code}): {msg}")
        raise JobError(f"API error on {path} (code {code}): {msg}")
    return payload


def graph(path, token, params=None, method="POST"):
    return _api_call(GRAPH_API, path, token, params, method)


def threads_api(path, token, params=None, method="POST"):
    return _api_call(THREADS_API, path, token, params, method)


def graph_upload_photo(page_id, token, file_path, published=True, caption=""):
    """Upload a local image file to a Page via multipart/form-data."""
    boundary = "----metamux" + uuid.uuid4().hex
    mime = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    fields = {"access_token": token,
              "published": "true" if published else "false"}
    if caption:
        fields["caption"] = caption
    parts = []
    for name, value in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                     f"name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"source\"; "
        f"filename=\"{os.path.basename(file_path)}\"\r\n"
        f"Content-Type: {mime}\r\n\r\n".encode() + file_bytes + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(
        f"{GRAPH_API}/{page_id}/photos", data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode("utf-8"))
        except Exception:
            raise JobError(f"HTTP {e.code} uploading photo to Page {page_id}")
    if isinstance(payload, dict) and payload.get("error"):
        raise JobError("photo upload failed: "
                       + str(payload["error"].get("message", payload["error"])))
    return payload


# ------------------------------------------------------------------ queue util

def ensure_dirs():
    for d in (QUEUE, DONE, FAILED, LOGS):
        os.makedirs(d, exist_ok=True)


def log(line):
    ensure_dirs()
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with open(PUBLISH_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{stamp}] {line}\n")


def parse_time(s):
    dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def load_job(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_job(path, job):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def is_url(value):
    return str(value).startswith(("http://", "https://"))


VIDEO_EXTS = (".mp4", ".mov", ".m4v")


def is_video_url(value):
    path = str(value).split("?")[0].split("#")[0].lower()
    return path.endswith(VIDEO_EXTS)


# ------------------------------------------------------------------ adapters

def publish_dryrun(job, alias=None):
    fake_id = f"dryrun-{job['id']}-{int(time.time())}"
    log(f"DRYRUN job={job['id']} -> {fake_id}")
    return fake_id


def publish_page(job, alias):
    """Facebook Page: text post, photo post (URL or local file), multi-photo."""
    acc = get_account(alias)
    page_id = acc.get("page_id")
    if not page_id:
        raise ConfigError(f"account {alias!r}: 'page_id' is not set")
    token = account_token(acc, "page_token", "graph_token")
    caption = job.get("caption", "")
    media = job.get("media", [])

    if not media:
        out = graph(f"{page_id}/feed", token, {"message": caption})
        return str(out["id"])

    if len(media) == 1:
        item = str(media[0])
        if is_url(item):
            out = graph(f"{page_id}/photos", token,
                        {"url": item, "caption": caption})
        else:
            out = graph_upload_photo(page_id, token, item,
                                     published=True, caption=caption)
        return str(out.get("post_id") or out["id"])

    # Multiple photos: upload unpublished, then attach them to one feed post.
    attached = []
    for item in media:
        item = str(item)
        if is_url(item):
            up = graph(f"{page_id}/photos", token,
                       {"url": item, "published": "false"})
        else:
            up = graph_upload_photo(page_id, token, item, published=False)
        attached.append(up["id"])
    params = {"message": caption}
    for i, media_id in enumerate(attached):
        params[f"attached_media[{i}]"] = json.dumps({"media_fbid": media_id})
    out = graph(f"{page_id}/feed", token, params)
    return str(out["id"])


def _wait_container(api_fn, token, container_id, status_field, ok="FINISHED",
                    tries=10, delay=3):
    for _ in range(tries):
        st = api_fn(container_id, token, {"fields": status_field}, method="GET")
        code = st.get(status_field)
        if code == ok:
            return
        if code == "ERROR":
            raise JobError(f"container {container_id} finished with ERROR")
        time.sleep(delay)
    raise JobError(f"container {container_id} not {ok} after {tries} checks")


def publish_ig(job, alias):
    """Instagram (professional account): single image, carousel, or Reel.

    Media must be public URLs - the Instagram Graph API does not accept
    local file uploads.
    """
    acc = get_account(alias)
    ig_id = acc.get("ig_business_id")
    if not ig_id:
        raise ConfigError(f"account {alias!r}: 'ig_business_id' is not set")
    token = account_token(acc, "graph_token", "ig_token")
    media = job.get("media", [])
    if not media:
        raise JobError("ig: a job needs at least one media URL")
    for item in media:
        if not is_url(item):
            raise JobError("ig: media must be public URLs "
                           "(the Graph API rejects local files): " + str(item))
    caption = job.get("caption", "")
    video = False
    if len(media) == 1:
        item = str(media[0])
        fmt = str(job.get("format", "")).lower()
        if fmt == "reel" or is_video_url(item):
            # The Graph API publishes single videos as Reels; there is no
            # separate feed-video type. "format": "reel" also covers video
            # URLs whose filename has no extension.
            container = graph(f"{ig_id}/media", token,
                              {"media_type": "REELS", "video_url": item,
                               "caption": caption, "share_to_feed": "true"})
            video = True
        else:
            container = graph(f"{ig_id}/media", token,
                              {"image_url": item, "caption": caption})
        creation_id = container["id"]
    else:
        children = []
        for item in media:
            if is_video_url(item):
                params = {"video_url": str(item), "is_carousel_item": "true"}
                video = True
            else:
                params = {"image_url": str(item), "is_carousel_item": "true"}
            child = graph(f"{ig_id}/media", token, params)
            children.append(child["id"])
        container = graph(f"{ig_id}/media", token,
                          {"media_type": "CAROUSEL",
                           "children": ",".join(children),
                           "caption": caption})
        creation_id = container["id"]
    if video:
        # Video containers process much longer than images.
        _wait_container(graph, token, creation_id, "status_code",
                        tries=60, delay=5)
    else:
        _wait_container(graph, token, creation_id, "status_code")
    out = graph(f"{ig_id}/media_publish", token, {"creation_id": creation_id})
    return str(out["id"])


def publish_threads(job, alias):
    """Threads: text-only post, or a single image/video post (public URL)."""
    acc = get_account(alias)
    user_id = acc.get("threads_user_id")
    if not user_id:
        raise ConfigError(f"account {alias!r}: 'threads_user_id' is not set")
    token = account_token(acc, "threads_token", "graph_token")
    text = job.get("caption", "")
    media = job.get("media", [])
    video = False
    if media:
        item = str(media[0])
        if not is_url(item):
            raise JobError("threads: media must be a public URL: " + item)
        if is_video_url(item):
            params = {"media_type": "VIDEO", "video_url": item, "text": text}
            video = True
        else:
            params = {"media_type": "IMAGE", "image_url": item, "text": text}
    else:
        params = {"media_type": "TEXT", "text": text}
    container = threads_api(f"{user_id}/threads", token, params)
    creation_id = container["id"]
    if video:
        _wait_container(threads_api, token, creation_id, "status",
                        tries=60, delay=5)
    else:
        _wait_container(threads_api, token, creation_id, "status")
    out = threads_api(f"{user_id}/threads_publish", token,
                      {"creation_id": creation_id})
    return str(out["id"])


ADAPTERS = {
    "page": publish_page,
    "ig": publish_ig,
    "threads": publish_threads,
    "dryrun": publish_dryrun,
}


def dispatch(target, job):
    if ":" in target:
        kind, alias = target.split(":", 1)
    else:
        kind, alias = target, None
    fn = ADAPTERS.get(kind)
    if fn is None:
        raise JobError(f"unknown target platform: {target!r}")
    if kind == "dryrun":
        return fn(job, alias)
    if not alias:
        raise JobError(f"target {target!r} needs an account alias, "
                       f"e.g. '{kind}:main'")
    return fn(job, alias)


# ------------------------------------------------------------------ runner

def process(path, job):
    jid = job.get("id", os.path.basename(path))
    try:
        results = {}
        for target in job.get("targets", []):
            results[target] = dispatch(target, job)
    except TransientError as e:
        job["last_error"] = str(e)
        job["blocked_until"] = (
            datetime.now(timezone.utc)
            + timedelta(minutes=TRANSIENT_BACKOFF_MIN)).isoformat()
        save_job(path, job)
        log(f"BLOCKED job={jid} {e}")
        print(f"[run] {jid}: {e} (retry in {TRANSIENT_BACKOFF_MIN} min)")
        return
    except JobError as e:
        job["attempts"] = int(job.get("attempts", 0)) + 1
        job["last_error"] = str(e)
        log(f"FAIL job={jid} attempts={job['attempts']} {e}")
        if job["attempts"] >= MAX_ATTEMPTS:
            save_job(os.path.join(FAILED, os.path.basename(path)), job)
            os.remove(path)
            print(f"[run] {jid}: FAILED {job['attempts']}x -> failed/")
        else:
            save_job(path, job)
            print(f"[run] {jid}: failed (attempt {job['attempts']}): {e}")
        return
    job["result"] = {"published_at": datetime.now(timezone.utc).isoformat(),
                     "post_ids": results}
    job.pop("blocked_until", None)
    job.pop("last_error", None)
    save_job(os.path.join(DONE, os.path.basename(path)), job)
    os.remove(path)
    log(f"OK job={jid} -> {results}")
    print(f"[run] {jid}: OK {results}")


def run_once():
    ensure_dirs()
    now = datetime.now(timezone.utc)
    for name in sorted(os.listdir(QUEUE)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(QUEUE, name)
        try:
            job = load_job(path)
        except Exception as e:  # a corrupt file must not kill the round
            print(f"[run] unreadable job {name}: {e}")
            continue
        if job.get("status") != "approved":
            continue
        blocked = job.get("blocked_until")
        if blocked:
            try:
                if parse_time(blocked) > now:
                    continue
            except Exception:
                pass
        try:
            due = parse_time(job["publish_at"])
        except Exception as e:
            job["attempts"] = int(job.get("attempts", 0)) + 1
            job["last_error"] = f"invalid publish_at: {e}"
            if job["attempts"] >= MAX_ATTEMPTS:
                save_job(os.path.join(FAILED, name), job)
                os.remove(path)
            else:
                save_job(path, job)
            continue
        if due > now:
            continue
        process(path, job)


# ------------------------------------------------------------------ commands

def cmd_init():
    ensure_dirs()
    for d in (QUEUE, DONE, FAILED):
        open(os.path.join(d, ".gitkeep"), "a").close()
    if os.path.exists(CONFIG):
        print("accounts.json already exists - left untouched.")
    elif os.path.exists(CONFIG_EXAMPLE):
        with open(CONFIG_EXAMPLE, encoding="utf-8") as f:
            content = f.read()
        with open(CONFIG, "w", encoding="utf-8") as f:
            f.write(content)
        try:
            os.chmod(CONFIG, 0o600)
        except OSError:
            pass
        print("created accounts.json from accounts.example.json "
              "(permissions 600). Fill in your IDs and tokens, "
              "then run: python3 metamux.py check")
    else:
        print("accounts.example.json is missing - cannot initialise.")
        return 1
    return 0


def cmd_add(src):
    job = load_job(src)
    if not job.get("id"):
        print("ERROR: a job needs an 'id' field")
        return 1
    if not job.get("publish_at"):
        print("ERROR: a job needs a 'publish_at' field (ISO 8601 with timezone)")
        return 1
    job.setdefault("caption", "")
    job.setdefault("format", "feed")
    job.setdefault("media", [])
    job.setdefault("targets", [])
    job.setdefault("status", "draft")
    job.setdefault("attempts", 0)
    ensure_dirs()
    dest = os.path.join(QUEUE, job["id"] + ".json")
    save_job(dest, job)
    print(f"queued: {dest} (status={job['status']}, targets={job['targets']})")
    return 0


def cmd_list():
    ensure_dirs()
    rows = []
    for name in sorted(os.listdir(QUEUE)):
        if not name.endswith(".json"):
            continue
        try:
            j = load_job(os.path.join(QUEUE, name))
        except Exception as e:
            rows.append(f"{name}\t<unreadable: {e}>")
            continue
        rows.append(f"{j.get('id')}\t{j.get('status')}\t{j.get('publish_at')}\t"
                    f"{j.get('targets')}\tattempts={j.get('attempts', 0)}")
    print("id\tstatus\tpublish_at\ttargets\tattempts")
    print("\n".join(rows) if rows else "(queue is empty)")
    done_n = len([f for f in os.listdir(DONE) if f.endswith(".json")])
    fail_n = len([f for f in os.listdir(FAILED) if f.endswith(".json")])
    print(f"done={done_n} failed={fail_n}")
    return 0


def cmd_check():
    try:
        accounts = load_accounts()
    except ConfigError as e:
        print(f"CONFIG: {e}")
        return 1
    status = 0
    for alias, acc in sorted(accounts.items()):
        try:
            token = account_token(acc, "graph_token", "page_token", "ig_token")
            me = graph("me", token, {"fields": "id,name"}, method="GET")
            print(f"[{alias}] graph: OK ({me.get('name', me.get('id'))})")
        except Exception as e:
            print(f"[{alias}] graph: FAIL ({e})")
            status = 1
        threads_token = resolve_secret(acc.get("threads_token", ""))
        threads_id = acc.get("threads_user_id")
        if threads_token and threads_id:
            try:
                me = threads_api("me", threads_token,
                                 {"fields": "id,username"}, method="GET")
                print(f"[{alias}] threads: OK (@{me.get('username', me.get('id'))})")
            except Exception as e:
                print(f"[{alias}] threads: FAIL ({e})")
                status = 1
    return status


def cmd_loop():
    print(f"[loop] MetaMux running, one round every 60s. pid={os.getpid()}")
    while True:
        try:
            run_once()
        except Exception as e:
            print(f"[loop] round error: {e}")
        time.sleep(60)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd = argv[1]
    if cmd == "init":
        return cmd_init()
    if cmd == "add":
        if len(argv) < 3:
            print("usage: metamux.py add <job.json>")
            return 1
        return cmd_add(argv[2])
    if cmd == "list":
        return cmd_list()
    if cmd == "run":
        run_once()
        return 0
    if cmd == "loop":
        return cmd_loop()
    if cmd == "check":
        return cmd_check()
    print(f"unknown command: {cmd}")
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
