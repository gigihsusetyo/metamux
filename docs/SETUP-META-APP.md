# Setting up your Meta developer app for MetaMux

MetaMux talks to the official APIs, so you need your own Meta developer app
and long-lived access tokens. This is a one-time setup (~20 minutes). Do it
with the Facebook account that owns (or administers) your Page, Instagram
professional account and Threads account.

## 1. Create the app

1. Go to [developers.facebook.com](https://developers.facebook.com) and
   register as a developer (phone + email verification).
2. **My Apps → Create App** → choose the **Business** type and give it any
   name (e.g. "My Content Scheduler").
3. In the app dashboard, add the **Instagram Graph API** use case/product.
   Later, also add the **Threads API** use case if you want Threads.

## 2. Permissions you need

In **Use cases → Instagram Graph API → Permissions**, add:

- `instagram_basic`
- `instagram_content_publish`
- `pages_show_list`
- `pages_read_engagement`
- `business_management`

For Threads (in the Threads API use case):

- `threads_basic`
- `threads_content_publish`

While your app is in development mode these permissions work for accounts
that hold a role on the app - which includes you. Add your own accounts
under **App roles** (Admin / Tester). For Threads, the target account also
has to *accept* the tester invitation inside the Threads app
(Settings → Account → Website permissions → Invitations).

## 3. Prerequisites on the accounts themselves

- Your **Instagram** account must be a **professional** (Business or Creator)
  account and **linked to your Facebook Page**.
- Your **Threads** account must be linked to that Instagram account.

## 4. Get a long-lived user token

1. Open **Tools → Graph API Explorer** in your app.
2. Select your app, click **Generate Access Token**, and approve the
   permissions listed above.
3. Exchange the short-lived token for a **long-lived user token** (±60 days):

   ```
   GET https://graph.facebook.com/v21.0/oauth/access_token
     ?grant_type=fb_exchange_token
     &client_id=<APP_ID>
     &client_secret=<APP_SECRET>
     &fb_exchange_token=<SHORT_LIVED_TOKEN>
   ```

   Meta does not offer a "choose the lifetime" menu - the lifetime is a
   property of the token type. Mark your calendar (or set a reminder) to
   refresh before day 60; `python3 metamux.py check` tells you when a token
   stops working.

## 5. Find your asset IDs

With your token in Graph API Explorer:

- **Page ID** - `GET /me/accounts` lists your Pages and their IDs.
- **Instagram business ID** - in that same response, each Page shows its
  `instagram_business_account.id`. That number is what MetaMux wants as
  `ig_business_id` (it is *not* your @handle).
- **Threads user ID** - call `GET https://graph.threads.net/v1.0/me` with a
  Threads token obtained through the Threads API login flow of your app.

## 6. Fill in accounts.json

```bash
python3 metamux.py init
```

Then edit `accounts.json`:

```json
{
  "accounts": {
    "main": {
      "graph_token": "env:METAMUX_MAIN_GRAPH_TOKEN",
      "page_id": "1234567890",
      "ig_business_id": "1234567890",
      "threads_token": "env:METAMUX_MAIN_THREADS_TOKEN",
      "threads_user_id": "1234567890"
    }
  }
}
```

Token values can be pasted literally, but the `env:` form is recommended:
export the tokens in your service environment and keep `accounts.json`
free of raw secrets. Either way: **never commit `accounts.json`** - it is
already in `.gitignore`.

Verify everything:

```bash
python3 metamux.py check
```

You should see `graph: OK` (and `threads: OK` if configured) for every
alias - with account names only, never token values.

## Platform notes & limits

- **Instagram media must be public URLs.** The Graph API fetches the image
  itself; local paths are rejected by MetaMux before any API call. (Carousels
  of 2+ URLs are supported.)
- **Facebook Page media** can be public URLs or local files - local files are
  uploaded with a multipart request; multiple photos are uploaded unpublished
  and attached to a single feed post.
- **Threads** posts here are text or a single image URL. Reply chains are on
  the roadmap.
- One token serves every Page/IG asset its user can access - additional
  brands under the same Meta account need only a new alias in
  `accounts.json` pointing at their IDs. Assets owned by a *different* Meta
  account need their own app grant/token, i.e. another alias with its own
  token.
