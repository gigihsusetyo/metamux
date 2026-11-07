<p align="center">
  <img src="docs/griz-bee-transparent.png" alt="Griz, the AI engineering agent behind MetaMux" width="180">
</p>

<h1 align="center">MetaMux</h1>

<p align="center">
  <b>One queue. Every Meta platform. Zero browser clicks.</b><br>
  A tiny, dependency-free, multi-account scheduler for Facebook Pages, Instagram and Threads - built on the official Meta Graph API &amp; Threads API.
</p>

<p align="center">
  <img alt="Python 3 stdlib only" src="https://img.shields.io/badge/python-3.10%2B%20%C2%B7%20stdlib%20only-blue">
  <img alt="License MIT" src="https://img.shields.io/badge/license-MIT-green">
  <img alt="Platforms" src="https://img.shields.io/badge/platforms-Facebook%20Page%20%C2%B7%20Instagram%20%C2%B7%20Threads-purple">
</p>

<p align="center">
  <i>Developed &amp; battle-tested inside <b>Muse</b> - Meta's personal AI agent environment.</i>
</p>

---

## The problem

MetaMux was born from a real operational bottleneck: running daily content
for multiple brands across Facebook Pages, Instagram and Threads.

Every existing route had a ceiling:

- **Native tools are fragmented.** Page and Instagram scheduling lives in
  Business Suite, Threads lives somewhere else, and nothing gives you one
  queue across platforms - let alone across several brands and accounts.
- **Connector-based posting hits an approval wall.** When an assistant or
  automation posts through platform connectors, every single action can
  demand a fresh manual approval, with no persistent "always allow". Fine
  for one post; unworkable at daily, multi-brand volume.
- **Browser automation is the expensive fallback.** Driving web dashboards
  with an agent burns compute and tokens, breaks whenever the UI shifts,
  and keeps tripping account-security checkpoints.
- **SaaS schedulers mean rent + trust.** A subscription per seat, your
  tokens and content on someone else's server, and still a separate silo
  per connected account.

What was needed: a **self-hosted scheduler on the official APIs** - one
queue, many accounts, with a hard approval gate between "content is
proposed" and "content is published", cheap enough to run forever on a
small VM. That is MetaMux.

## What MetaMux does

- **File-based queue** - one JSON file per post (`queue/` → `done/` / `failed/`). No database, no web server, nothing to migrate. `ls` is your monitoring tool.
- **Approval gate** - the daemon only publishes jobs with `"status": "approved"`. Drafts are never touched. A human (or an AI agent on their behalf) proposes content; a human approves; the daemon publishes. In production use, this gate is what made unattended publishing trustworthy.
- **Multi-account mux** - define as many account sets as you like in `accounts.json`. A target is `"<platform>:<alias>"` (`page:main`, `ig:studio`, `threads:main`, ...), so one job can fan out across platforms *and* brands in a single run.
- **Official APIs only** - Facebook Page posts and Stories, Instagram container publishing (single image, carousel, Reels, and Stories) and Threads publishing (text, image, video), exactly the flows Meta documents. No scraping, no unofficial endpoints.
- **Failure semantics that respect the platform** - ordinary failures retry once, then move to `failed/`. Rate limits back the job off for 15 minutes *without* burning its attempts.
- **Secrets stay secret** - tokens live in `accounts.json` (chmod 600, git-ignored) or in environment variables via `"env:VAR_NAME"` references. Nothing secret is ever logged.

## Who it's for

Meta power users who have outgrown one-by-one posting: **creators, Page
admins, social media managers, and small agencies or indie operators
running several brands** across Facebook, Instagram and Threads - and who
want scheduling they fully own instead of renting.

## Two ways to run it

**1. Standalone.** No AI involved: write job files by hand (or from any
script), approve them, and let the daemon or a cron/systemd timer publish.
It is just Python's standard library - if a machine runs Python 3.10+, it
runs MetaMux.

**2. Inside an AI / MCP environment.** MetaMux's interface is deliberately
agent-shaped: files in, files out, a plain CLI. Any MCP-capable assistant
or automation that can write a JSON file and run a command can operate it -
the agent drafts jobs, the human flips `status` to `approved`, the daemon
publishes and files the receipts in `done/`. No SDK, no plugin, no lock-in
to any particular agent platform.

## Quick start

```bash
git clone https://github.com/gigihsusetyo/metamux.git
cd metamux

python3 metamux.py init     # creates folders + accounts.json from the example
$EDITOR accounts.json       # fill in your Page / IG / Threads IDs and tokens
python3 metamux.py check    # verify every token (prints names, never tokens)

cp examples/job-single.json my-first-job.json   # edit caption, media, time
python3 metamux.py add my-first-job.json
python3 metamux.py list
python3 metamux.py run      # one round - or run it as a daemon:
python3 metamux.py loop
```

You need a Meta developer app and long-lived tokens first - the full
walkthrough is in **[docs/SETUP-META-APP.md](docs/SETUP-META-APP.md)**.

## A job is just JSON

```json
{
  "id": "launch-post-001",
  "caption": "We are live!",
  "media": ["https://example.com/launch.jpg"],
  "targets": ["page:main", "ig:main", "threads:main"],
  "publish_at": "2026-01-01T09:00:00+07:00",
  "status": "approved",
  "attempts": 0
}
```

| Field | Meaning |
|---|---|
| `id` | Unique job name; becomes the filename in `queue/` |
| `caption` | The exact text that will be published |
| `media` | Media list. **Instagram & Threads require public URLs.** Facebook Pages accept public URLs *or* local file paths. |
| `format` | Optional. `feed` (default), `reel`, or `story`. A single video URL is auto-detected as a Reel on Instagram and a video post on Threads even without this field; `reel` covers extension-less video URLs. `story` takes exactly one photo or video and publishes it as an Instagram Story or a Facebook Page Story - no caption, no stickers (the APIs offer neither), and Threads targets are rejected because Threads has no Stories |
| `targets` | Any mix of `page:<alias>`, `ig:<alias>`, `threads:<alias>`, plus `dryrun` for testing |
| `publish_at` | ISO 8601 with timezone. The scheduler owns the clock - adapters publish "now" when a job falls due |
| `status` | `draft` (never published) or `approved` (will publish when due) |

## Run it as a service

A ready-to-edit systemd unit ships in [`metamux.service`](metamux.service):

```bash
sudo cp metamux.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now metamux
```

## Project layout

```
metamux.py            the whole scheduler (stdlib only)
CHANGELOG.md          what changed in each version
accounts.example.json config template - copy to accounts.json
examples/             sample jobs
queue/  done/  failed/  logs/    runtime state (git-ignored)
docs/                 setup guide + artwork
tests/smoke_test.py   end-to-end dry-run test, no network needed
```

## Test

```bash
python3 tests/smoke_test.py
python3 tests/test_adapters.py
```

The smoke test runs the real CLI in a temp folder: an approved `dryrun`
job must land in `done/` with a result, and a `draft` job must stay
untouched in `queue/`. The adapter tests stub the Meta APIs and assert
that every job shape (image, Reel, carousel, Threads text/video) produces
the right API calls - no network, no tokens.

## Roadmap

**v1.1 - Video, same flows** ✅ *shipped*
- Instagram Reels (`media_type: REELS`, public video URLs)
- Threads video posts (`media_type: VIDEO`)

**v1.2 - Facebook Page Reels**
- Page Reels via the three-phase `video_reels` upload (start → upload → finish)

**v2.0 - Stories everywhere** ✅ *shipped*
- A `"format"` field in the job schema: `"feed"` | `"reel"` | `"story"`
- Instagram Stories (`media_type: STORIES`) - plain media only; the API
  cannot attach interactive stickers (link, poll, location)
- Facebook Page Stories (`photo_stories` for photos, three-phase
  `video_stories` for video)
- Why this matters: Meta offers **no native scheduling for Reels or
  Stories** - they must be published at the moment they go live, which is
  exactly the timing layer MetaMux's daemon already provides.

**v2.x - Beyond Meta (optional)**
- An experimental, opt-in X (Twitter) adapter (`x:<alias>`), kept outside
  the Meta core: it needs its own OAuth flow and is subject to X's own
  API pricing.

**Anytime**
- Threads reply chains / thread series
- Optional media hosting helper for local files (S3 / Drive public links)
- Per-account rate-limit awareness

Issues and PRs are welcome.

## About this project

MetaMux was **conceived, specified and directed by Gigih Susetyo**, an AI
orchestrator and AI software engineer. It grew out of his production content
operations - daily publishing across multiple Meta brands - where he
defined the problem, the workflow and the safety model:
*propose → approve → publish*, with verification at every step.

Engineering implementation was executed by **Griz**, an AI engineering
agent (powered by Muse Spark, Meta), working under Gigih's direction,
specifications and review. The bee in the header is Griz. The point of the
project is the operating model as much as the code: an orchestrator who
sets the spec and the guardrails, an agent that builds and runs inside
them, and a daemon that never publishes anything a human hasn't approved.

The production system MetaMux is distilled from was built and
battle-tested inside **Muse, Meta's personal AI agent environment**,
where an AI agent operates real multi-brand publishing workflows under
human direction, specification and review. Open-sourcing it meant removing
every platform dependency: MetaMux now runs anywhere Python runs, with any
agent stack - or none at all. **Muse is its birthplace, not a
requirement.**

## License

MIT - see [LICENSE](LICENSE). In short: free to use, copy, modify and
distribute, including commercially; keep the copyright and license notice;
no warranty. Your content, accounts and tokens remain entirely yours -
MetaMux is self-hosted and phones nothing home.

---

## 🇮🇩 Ringkasan Bahasa Indonesia

MetaMux lahir dari masalah nyata: menjalankan konten harian multi-brand di
Facebook Page, Instagram, dan Threads. Jalur bawaannya terpisah-pisah,
posting lewat konektor mentok di persetujuan manual tiap aksi tanpa mode
"selalu izinkan", otomasi browser boros dan rapuh, dan scheduler SaaS
berarti biaya langganan plus menyerahkan token ke pihak ketiga.

Solusinya: scheduler **self-hosted** di atas API resmi Meta. Satu file
Python (stdlib murni, tanpa dependensi), antrean file JSON - satu file per
konten, folder `queue/` → `done/` / `failed/`, daemon memproses tiap 60
detik. Hanya job berstatus `approved` yang tayang; job `draft` tidak pernah
disentuh. Multi-akun didukung lewat alias di `accounts.json` (target
seperti `ig:main`, `page:brand2`). Bisa jalan **standalone** (CLI +
systemd), atau dioperasikan agen AI di lingkungan MCP mana pun - agen
menulis job, manusia menyetujui, daemon mempublikasikan. Panduan setup app
Meta ada di `docs/SETUP-META-APP.md`. MetaMux sendiri dikembangkan dan
diuji dalam produksi di dalam **Muse** (lingkungan agen AI personal dari
Meta) - tempat kelahirannya, bukan syarat pakainya: setelah di-open-source
ia berjalan di mana saja.
