# PROGRESS

_Last updated: 2026-10-15_

The v1 codebase (FastAPI + vanilla JS, preserved in `legacy/`) was rebuilt into a production
architecture. The stack choices were made with the founder: **FastAPI backend (no Supabase) + Next.js
frontend, video included, Google + email/password auth (no phone OTP).** Everything else follows
`PROVOK_BUILD_SPEC.md`.

## Status by spec phase

| Phase | Status | Notes |
|---|---|---|
| 0 Scaffold | ✅ | Next.js 16 app, FastAPI, ARQ worker, docker-compose, CI, Sentry (API + worker) |
| 1 Data + Auth | ✅ | 24 tables w/ CHECK constraints; Argon2; rotating refresh tokens w/ reuse detection; email verify/reset; Google OAuth (PKCE + nonce + JWKS) |
| 2 Debate engine | ✅ | Pure state machine (48 tests), deadlines + sweeper, realtime, all endpoints |
| 3 Core UI | ✅ | Feed (mobile swipe / desktop grid), Create + Matchup Picker, Arena, Challenges |
| 4 LLM gateway + Swarm | ✅ | LiteLLM gateway with cost logging, versioned prompts, 4-agent swarm, HvA + AvA |
| 5 Ledger + Judge | ✅ | Claim Board, citation checks (SSRF-safe), blinded swap-test judge, Elo, model leaderboard, Verdict Reveal |
| 6 Voting + Sharing | ✅ | Per-round hidden tallies, weighting, momentum bar, dynamic OG images, share flows |
| 7 Credits + Payments | ✅ | Idempotent ledger, Razorpay orders/verify/webhook, wallet |
| 8 Safety + Ops | ✅ | Topic policy, moderation, injection defences + strikes, rate limits, reports, admin, spend kill-switch, readiness check |
| 9 Video | ✅ code / ⚠️ untested live | LiveKit tokens, server-authoritative mic permissions, Deepgram STT → turns, egress recording, ffmpeg clips |
| 10 Polish + Launch | 🟡 | Empty/loading/error states, onboarding quick-start, featured AvA cron, analytics + launch metrics dashboard |

## Verified

- **172 backend tests pass** (real Postgres/Redis), ruff clean, migrations round-trip with no drift.
- **Frontend**: typecheck, lint (React Compiler rules) and production build all pass.
- **Live end-to-end run with real models** (Qwen vs GPT-OSS on Groq): a full 10-turn AvA debate ran to
  a judged verdict through the real worker, surviving free-tier rate limits via backoff + auto-resume,
  with 30 extracted claims, real citations, and a coherent explained verdict.
- SSR metadata and OG share images render (≈100 KB PNG, WhatsApp-safe).

That live run found and fixed real bugs that mocks could not: wrong Groq model id in the old `.env`,
Groq strict-JSON rejections, reasoning-model empty outputs, and a **lock bug where judging held a row
lock that blocked every child insert for minutes** (now `FOR NO KEY UPDATE` + lock-free judging, with a
regression test).

## Browser E2E (Playwright)

`apps/web/e2e` — 38 tests (desktop + mobile): first debate vs AI through to the verdict, human-vs-human
challenge → join → turns → spectator vote, auth errors, no page errors/hydration mismatches, no horizontal
scroll at 360px, security headers, share metadata. Runs in CI against the real stack with `LLM_FAKE=true`.
The browser pass found and fixed: a paywall on "debate an AI now" (flagship default), a hydration race in
the nav, a stale-response race that resurrected finished turns, a lazy-load crash on `updated_at`, the
fixed dock covering Submit, and a client-side vote rule contradicting the server.

## Database (2026-10-10)

- Dev database is now **Neon** (Postgres 18). The schema is migrated (`0001`), and the app connects
  through the `-pooler` host with `DATABASE_PGBOUNCER=true`. Run migrations against the direct (non-pooler) host.
- `DATABASE_URL` accepts libpq-style URLs as copied from Neon/Render: `sslmode` is translated to asyncpg's
  `ssl` and `channel_binding` is dropped (`core/config.py`, tested in `tests/test_config.py`).
- The old Render URL is kept commented out in `.env`; it has the legacy v1 schema.

- Live run on Neon found: Gemini 3.x Flash "thinks" inside its token budget, so short JSON replies (critic, 400 tokens)
  were truncated and the turn failed with `swarm_error`. Fixed: Gemini 2.5/3.x get the reasoning-model budget, and
  an unparseable strategist/critic reply is skipped instead of failing the turn (regression test in `test_debate_flow.py`).

## Invites (2026-10-10)

- **Challenge someone** now also emails the invitee (verified emails only), not just an in-app notification.
- **Invite link**: a new corner type. The open seat gets a secret token; only `/d/{id}?invite=<token>` can take it
  (checked server-side, `invite_link_required` otherwise). Only the creator ever receives the token; link debates
  never appear in Open Challenges. The creator gets "Send on WhatsApp" / "Copy invite link". The token survives
  sign-up from the auth sheet, including Google sign-in. Migration `0002` adds `sides.invite_token`.
- Fixed: the arena header flipped between collapsed/expanded on short pages (scroll threshold without hysteresis).
- The verification email now brings a new user back to where they signed up (`next`, validated server-side), so an
  invited newcomer lands on the invite after confirming their email.

## Performance + monitoring (2026-10-10)

Lighthouse 13.5 mobile (simulated slow 4G, 4x CPU), production build:

| Page | Before | After | LCP | TBT | CLS |
|---|---|---|---|---|---|
| Home | 55 | 80 | 5.4s → 4.2s | 1143 → 280ms | 0.001 |
| Create | 39 | 71 | 5.9s → 4.6s | 785 → 483ms | 0.461 → 0.003 |
| Arena | (trace failed) | 68 | 4.5s | 627ms | 0 |
| Verdict | 57 | 78 | 5.1s → 4.1s | 981 → 320ms | 0.079 |

Accessibility and best practices are 100 on all four. What changed:
- The live dot animated `box-shadow`, repainting every frame under the blurred header and grain overlay
  (28s of rendering during a Lighthouse run). It now animates transform/opacity on a pseudo-element (0.3s).
- `motion` uses `LazyMotion` + `m` components; the animation engine (`domMax`) loads after hydration.
- LiveKit (~150 KB) loads only for video debates (`next/dynamic`); before, every feed card's prefetch pulled it.
- `/new` reserves the wizard's height while it loads (layout shift 0.46 → 0.003).
- `/auth/refresh` with no session returns 204 instead of 401 (a red console error on every signed-out visit).
- `--text-faint` raised to WCAG AA contrast in both themes; the feed has a screen-reader `h2` for heading order.
- Remaining LCP is the hero heading repainting when the display font arrives; `display: optional` would fix it at
  the cost of the fallback font on first visits. Not changed (design call).

Web error reporting: `NEXT_PUBLIC_SENTRY_DSN` turns on Sentry for the browser and the Next server (`@sentry/nextjs`
10.75.3). In the browser the SDK is downloaded only when the first error happens (zero cost on healthy loads);
verified end to end against a fake ingest. Source-map upload is not set up yet (stack traces are minified).

## Pre-launch security review (2026-10-10)

Reviewed: auth/sessions (JWT pinned to HS256 with exp/typ/aud/iss, rotating refresh + reuse detection, hashed
email tokens, OAuth state/PKCE/nonce, safe `next` redirects), authorization on every route (ownership checks on
payments, notifications, debate actions; hidden debates; video publish rights), payments, SSRF fetcher, prompt
injection, XSS sinks (only a static theme script; external links are http(s)-only with `rel=noopener nofollow ugc`),
websocket origin + ticket auth, rate limits on LLM-spending and spammable endpoints, production config guards, and
dependency audits (`npm audit --omit=dev`, `pip-audit`: 0 known vulnerabilities).

Fixed:
- Checkout signature verification accepted an HMAC under an **empty** Razorpay secret. Orders can't be created
  without keys, but if the secret were ever unset (bad deploy, rotation) open orders could be "paid" with a forged
  signature. Now rejected (regression test).
- Production now refuses to boot with Razorpay keys but no `RAZORPAY_WEBHOOK_SECRET` (every webhook would be
  rejected, so a payment whose browser never came back would never be credited).

## Infrastructure (2026-10-10)

Hosting moves straight to **AWS Mumbai** (founder's decision; $200 credits). `infra/` holds Terraform for one
small EC2 server per environment (Caddy + web + API with embedded worker + Redis, Postgres on staging), ECR, an S3
media bucket, SES, an SSM SecureString for the server `.env`, and a GitHub OIDC deploy role. `.github/workflows/
deploy.yml` builds both images, pushes them and deploys over SSM after CI passes on `main` (skipped until the
`AWS_DEPLOY_ROLE_ARN` repo variable exists). Runbook: `infra/README.md`.

- Chosen over ECS/ALB/NAT for now: ~$20–25/month for staging vs $60+, so the credits last ~8–10 months.
  Same images move to ECS + RDS later.
- New `EMAIL_PROVIDER=ses` (IAM role credentials, no SMTP password).
- Verified locally: `terraform validate`, compose config with a dummy env, script syntax, workflow YAML.
  **Not yet applied to AWS** (needs the founder's AWS login).

### Staging is live (2026-10-10)

- **https://65-0-216-112.sslip.io** (EC2 `i-08efaf2502bf96a8b`, Mumbai). First deploy from GitHub Actions passed;
  `/health/ready` reports database, Redis and worker ok; Let's Encrypt certificate issued. `akkiyolo` is admin.
- AWS account is on the **Free plan**: $199.91 credits, **expires 2027-01-17**. Upgrade to the Paid plan before then
  (credits carry over) or AWS closes the account. Budget alert `provok-monthly` emails at 80% of $30/month
  (gross cost, credits excluded).
- SES is in the sandbox with one verified sender (the founder's Gmail): only verified addresses receive mail,
  and Gmail-from-SES lands in spam. Fix before launch: own domain (DKIM) + SES production access.
- Found while applying: GitHub's OIDC token now uses `repo:owner@<id>/name@<id>:...`; the deploy role accepts both
  formats (`github_repository_ids`). Git Bash rewrote `/provok/...` SSM names into Windows paths
  (`MSYS_NO_PATHCONV=1` in the scripts). The SSM agent can miss the instance role on first boot (reboot fixes it).
- The founder's network (Fortinet DNS filter) blocks `*.sslip.io`; another reason to get a real domain.
- Verified by the founder on staging: email sign-up + verification (SES, landed in spam), Google sign-in, and a
  human-vs-AI debate with AI replies. 3 of 6 Gemini calls in that debate got Google's 503 "high demand" (free tier);
  retries recovered. Paid keys (launch checklist #1) remove this.

### Domain: provok.in (2026-10-11)

- Bought at GoDaddy (expires 2027-10-10); GoDaddy's post-purchase hold lifted after Aadhaar KYC.
- DNS in Route 53 (`infra/terraform/dns.tf`); **staging is https://staging.provok.in** (sslip.io retired),
  `provok.in` itself is kept for production. Google OAuth has the new origin + redirect.
- SES domain `provok.in` verified (DKIM; custom MAIL FROM `mail.provok.in`; DMARC `p=none`); mail now sends from
  `noreply@provok.in`. Still in the SES sandbox: request production access before launch.
- Gemini's free tier (~20 requests/day) ran out mid-debate (429), so staging defaults to Groq
  (`DEFAULT_SWARM_MODEL_KEY=groq_gpt_oss`). Debates already on Gemini resume when the quota resets.
- Deploy fix: image tags are now `<sha>-<hash of baked web settings>` and existing images are reused, so re-running
  a deploy (e.g. after an env change) no longer fails on ECR's immutable tags.
- FortiGuard filters (common on office/college networks) block newly registered domains; submit provok.in for
  categorisation before launch.
- SES production access requested 2026-10-11; AWS's first review asked for more detail (case 179169689700462,
  shown as DENIED in the API). The founder replied with volume, opt-in, bounce/complaint handling, auth records and
  sample emails. **Fallback if refused:** Resend (`EMAIL_PROVIDER=resend` is already supported): add its DKIM/SPF
  records to Route 53 and switch the env. Deferred until AWS answers.
- Gemini's 04:00 UTC featured debate stalled on the exhausted quota; hidden. Featured debates now use Groq models.
- Two featured AvA debates (Qwen vs GPT-OSS on Groq) paused on Groq's free output-tokens-per-minute limit, auto-resumed
  and completed with verdicts. Both went to the GPT-OSS side, judged by GPT-OSS, with swap-test runs disagreeing:
  likely self-preference, possible only because Groq is the sole enabled provider. With paid keys, keep a judge
  from a different provider than the debaters (`JUDGE_MODEL_KEYS`).
- CI e2e had been failing since `90d27d7`: `wait-on` probes with HEAD and `/health` answered 405, so the job timed
  out before any test ran. Health endpoints now accept HEAD (monitors use it too) and CI waits with `http-get://`.
- Video: LiveKit Cloud keys added and verified (ListRooms). Deepgram signup kept failing on the founder's side, so
  speech-to-text is untested; recording is off (`VIDEO_RECORDING_ENABLED=false`) until LiveKit egress gets S3
  credentials for `recordings/` (and that prefix needs a public-read or signed-URL decision).

### Uptime monitoring (2026-10-11)

- Route 53 health check on `https://staging.provok.in/health/ready` (every 30s, many regions; passes only when the
  body has `"worker":"ok"`) → CloudWatch alarm (us-east-1) → SNS email to the founder, on failure and on recovery.
  `staging.sh stop` pauses the alarm's actions; `start` resumes them after 5 min. `infra/terraform/monitoring.tf`.
- Gemini models are disabled in the staging registry (free tier too small); re-enable in Admin → Models with a
  billed key.

### Android app (2026-10-11)

- `apps/android`: a **Trusted Web Activity** (android-browser-helper 2.7.4, AGP 9.4.1, Gradle 9.8.1, compileSdk 37,
  targetSdk 36, minSdk 24). Chosen over a native/React Native app as the simplest path: every web feature works
  unchanged and web deploys reach the app. Flavours `staging` (`in.provok.app.staging` → staging.provok.in) and
  `production` (`in.provok.app` → provok.in). Native adaptive + themed icon, splash, Play icon and feature graphic.
- Digital Asset Links: the API serves `/.well-known/assetlinks.json` from `ANDROID_PACKAGE` / `ANDROID_CERT_SHA256`
  (staging is configured with the upload key). After the first Play upload, add Play's app-signing fingerprint.
- Upload keystore `apps/android/provok-upload.jks` + `keystore.properties` are gitignored and exist only on the
  founder's laptop: **back them up**. Signed builds in `apps/android/dist/` (staging APK, production AAB 1.0.0).
- First install crashed on launch (Samsung A34, Android 16): android-browser-helper 2.7.x enables
  `ManageDataLauncherActivity` on first run and throws if the manifest doesn't declare it. Declared it (plus
  `manageSpaceActivity`); verified on the device over adb: opens full-screen with no URL bar (asset links verified).
- `.github/workflows/android.yml` builds the app on changes (separate from CI so it never blocks web deploys).
- Store listing, content rating, data safety and target-audience answers: `apps/android/play-store/LISTING.md`.
- **In-app purchases are hidden** (Play's payments policy: no outside checkout for digital goods and no pointers to
  buying elsewhere). The app launches `/?app=android`; `lib/platform.ts` records it (or an `android-app://`
  referrer) in sessionStorage, which the app's session doesn't share with normal Chrome tabs. Inside the app the
  wallet shows balance and history only, and "not enough credits" says human debates are free instead of "Top up".
  Credits bought on the website work in the app. E2E: `inside the Android app the wallet ... no purchases`.
- New personal Play accounts need a 12-tester, 14-day closed test before production.
- Local build note: on the founder's network Java could not reach Gradle's download mirror, so the wrapper was
  generated with `--no-validate-url`; `./gradlew` downloads Gradle normally elsewhere (CI).

### Full app review, web + Android (2026-10-15)

Walked every page (98 views: logged out, user, admin × desktop and Pixel 7) on a seeded local stack. Fixed:
- **Signed-in data missing on first load** (own profile offered Follow/Block, "Who to follow" suggested yourself,
  your likes/bookmarks not shown): a page's first queries ran before the session was restored and the anonymous
  answer stuck in the cache. `api()` now waits for the one-time session restore before its first request.
- **Pinned post shown twice** on the profile: the Posts tab now leaves it out (it's on top already).
- **Walkover:** a side that let every turn run out now loses automatically (no judge call, ratings update), so a
  judge can never hand the win to someone who never argued.
- Verdict: "Judged by" shows the model's name (was the internal key); the scorecard scrolls cleanly on phones.
- Mobile: the turn composer header wraps whole items; no footer under a chat thread.
- CI on the S3 commit had failed on one stale test (`views` count), so S3 never deployed; fixed and deployed.
- Auto-resume of paused debates: the retry counter's 1-day expiry was refreshed on every sweep, so "3×/day" was
  really "3× ever"; retries now also back off (5, 15, 45 min). Found via a featured AvA on staging paused by a
  Groq failure on 2026-10-15 (resume it from `/admin → Paused`).
- **All AI on Amazon Bedrock** (founder's call, 2026-10-15): Groq, Gemini and direct-Anthropic models are gone from
  the seed and disabled by migration `0007` (rows kept for history); GPT-OSS 120B now debates via Bedrock and
  unfinished debates moved over. Defaults: debater Qwen3, utility GPT-OSS → Nova Lite, judges DeepSeek → Qwen.
  `GROQ_API_KEY`/`GEMINI_API_KEY` are no longer read. Tests pin the model settings (a dev `.env` can't change them).
Android: TWA config checked (asset links, launch URL, in-app purchase hiding); nothing to change.

### Social network, phase S3: a full social app (2026-10-14)

Founder feedback after testing S1–S2: "could have been better with way more features". S3 adds (migration `0006`):
- **Profiles:** cover photo (`/me/banner`, 3:1 WebP under `avatars/`), location, website (validated, http(s)),
  pinned post (`/posts/{id}/pin`, shown first on the Posts tab), official accounts (`users.is_official`, ✓ badge).
- **Posts:** view counts (one per person/IP per post per hour via Redis `SET NX`; authors' own views don't count),
  "Liked by" list (`/posts/{id}/likes`), link preview cards (first URL; `link_preview` job fetches the page head
  through the SSRF-safe fetcher, `safe_fetch.fetch_html`; text-only values, http(s) images only).
- **Polls:** 2–4 options, 1h–7d; one final vote per person; results hidden until you vote, the poll ends, or you're
  the author. A close poll (≥4 votes, top option ≤65%) offers **Poll → Debate**: an open challenge from the post
  (`challenge-question?mode=open`).
- **Daily Debate:** every day at `DAILY_DEBATE_UTC` (default 00:30 = 06:00 IST) the official **@provok** account
  (reserved username, created on first run) posts a question from the bank with a Yes/No poll, and an AI-vs-AI
  featured debate starts on it, linked to the post. `/daily`; shown atop Home (For you) and Explore.
  `cli daily-debate` runs it now (idempotent per day).
- **Explore** (`/explore`): search, Daily Debate, live debates, top posts today, who to follow (people your follows
  follow, then popular accounts), trends. **New posts banner** on Following (`/feed/new?since=`, polled every 30s).
- **Direct messages** (`/messages`): one conversation per pair; anyone verified can message anyone not blocked;
  strangers land in **Requests** until you reply and don't light the unread badge; threads poll every 5s; account
  deletion removes the user's conversations; export includes sent messages. Not end-to-end encrypted (privacy
  page says so). `RL_DM_USER`, `RL_DM_NEW_USER`.
- Navigation: top Home · Explore · Arena · Challenges · Leaderboard + Messages and Notifications icons; mobile
  Home · Explore · + · Messages · You (Arena and the leaderboard are linked from Explore).
- Tests: `test_social_more.py` (13) and browser journey "polls, explore and direct messages".
- Later: realtime push over the existing user websocket instead of polling, GIF/video, threads (multi-post),
  edit window, communities, Hindi UI, voice posts, live debate rooms, DM reports.

### Social network, phase S2: what X can't do (2026-10-12)

- **Challenge a post** (⚔ on every post): the utility model turns the post into a neutral motion and says which
  side its author holds (`post_question` prompt, post text delimited + neutralised); the challenger takes the other
  side and the author is invited (existing invite + email). Debates keep `source_post_id`; posts show a debate count
  and the post page lists them ("Settled in the Arena"). Inviting someone across a block is now refused (it wasn't).
- **AI fact-check** (⋯ → Fact-check with AI): one check per post, shared by every reader; a background job searches
  the web (Tavily) and the utility model rates the post (`accurate` … `false`, `unverifiable`, or `opinion`) with up
  to 3 sources. No sources → `failed` (retryable after 10 min). `RL_FACTCHECK_USER` 20/day.
- **Translate** posts to Hindi/English, cached per post and language (`post_translations`). `posts.lang` is detected
  from the script (Devanagari, Bengali, Gurmukhi, Gujarati, Odia, Tamil, Telugu, Kannada, Malayalam; romanised
  Hindi reads as English). `RL_TRANSLATE_USER`.
- **Credibility:** `public_user` carries `debates` (finished); post cards show a ◆ rating badge once it's above 0.
- Migration `0005`. Tests: `test_post_ai.py` (14), browser journey "challenge: a post becomes a debate…".
  208 backend tests and 44 browser tests pass.
- Known: the existing "private invite link" browser test (mobile) flaked once under low laptop memory and passed
  on retry; untouched code. Watch it in CI.
- Not yet: full Hindi UI (all screens), automatic fact-checks on viral posts (cost), translation to other Indian
  languages. Candidates for S3 with ranking, communities and live rooms.

### Social network, phase S1: the social core (2026-10-12)

Direction (founder, 2026-10-12): grow Provok from a debate app into a **debate-first social network for India**.
Defaults taken where the founder didn't choose (CLAUDE.md rule 9): debates stay the differentiator, politics,
religion and caste stay blocked at launch, Hindi comes in phase S2. Plan: S1 social core → S2 post→debate
"Challenge", AI fact-checks, credibility, Hindi + translation → S3 ranking, communities, live rooms.

- **Data** (migration `0004`): `posts` (post/reply/quote/repost; reposts are rows so they sit in timelines at
  repost time; `root_id` for threads; denormalised counters), `post_media`, `post_likes`, `bookmarks`,
  `post_hashtags`, `user_blocks`, `user_mutes`; reports can target posts.
- **API** (`api/posts.py`, `services/posts.py`): create/delete posts with up to 4 images (re-encoded to WebP, EXIF
  stripped, ≤2048px), replies/quotes/reposts, likes, bookmarks, hashtags incl. Indian scripts, @mentions; feeds
  `Following` (cursor) and `For you` (engagement / age^1.5, follow boost, 72h window, 8 pages); user tabs
  (posts/replies/media/likes), threads (ancestors + replies), tag pages, trends (≥2 distinct people in 24h),
  search; blocks (hide both ways, end follows, stop replies/quotes/follows) and mutes (silent). Following and
  notifications for like/reply/quote/repost/mention/follow skip blocked and muted users.
- **Timelines are fan-out on read** from indexed Postgres. Simple and correct at our scale; a Redis fan-out cache
  can sit in front later without API changes.
- **Safety:** topic blocklist and link-spam check at write time; an async `moderate_post` job hides flagged posts
  and tells the author and admins; admin `hide_post`/`unhide_post`; rate limits `RL_POST_USER*`,
  `RL_REACTION_USER`, `RL_MEDIA_USER`. Posting/liking/reposting require a verified, non-restricted account.
  Account deletion deletes posts, likes, bookmarks, blocks and mutes; export includes posts and likes.
- **Web:** `/home` (For you / Following, inline composer, Trends), `/p/[id]` (thread + reply box, share metadata),
  `/tag/[tag]`, `/bookmarks`; profile tabs Posts/Replies/Photos/Likes/Debates with mute/block; search shows
  posts; app-wide compose sheet (+ on mobile offers Post or Debate). The Android app gets all of it with no
  release (TWA). `/` is still the Arena; making `/home` the root is a later call.
- **Infra:** media bucket makes `posts/*` public (Terraform; apply before images load).
- Tests: 14 backend (`test_posts.py`), browser journey "social: post, follow, like, reply…". 194 backend tests,
  42 e2e pass.

### Accounts and wiring (2026-10-12)

- Legal pages show the founder's details (GitHub variables `NEXT_PUBLIC_LEGAL_*`, `NEXT_PUBLIC_GRIEVANCE_OFFICER`).
- Inbound mail: ImprovMX forwards `*@provok.in` (catch-all) to the founder's Gmail. MX + apex SPF via
  `extra_dns_records` in `staging.tfvars` (the staging stack owns the zone).
- Sentry (US region): backend DSN in the server env; a test event from the server arrived tagged staging + release.
  Web DSN: GitHub variable `NEXT_PUBLIC_SENTRY_DSN`.
- AWS credits covered all usage so far ($1.18 by 2026-10-11); Bedrock charges not yet in Cost Explorer.
- AWS Activate (Founders tier) application in progress. **SES production access granted** (checked 2026-10-15:
  50,000 emails/day, 14/s), so verification and reset emails reach any address.
- Spend to 2026-10-15: $4.94 of usage (EC2 $2.94, Route 53 $0.71, VPC $0.56, Bedrock $0.69), all paid by credits;
  $194.97 of credits left.

### AI models on Amazon Bedrock (2026-10-11)

- The AWS account's promotional credits (~$120 would otherwise expire unused on 2027-01-17) pay for Bedrock. LiteLLM
  calls it through the server's IAM role (`BEDROCK_REGION`; IAM `BedrockInvoke`, invoke only); no API keys.
- Live and verified through LiteLLM (text + JSON + cost): Qwen3 235B, DeepSeek V3.2, Kimi K2.5, Mistral Large 3,
  GLM-5 (selectable, standard tier); GPT-OSS 120B and Nova Lite (utility); DeepSeek and Qwen judges.
  `provider` = the model's maker, so judges stay cross-family. Staging: default debater Qwen3, utility GPT-OSS →
  Nova Lite → Groq, judges DeepSeek → Qwen → Groq.
- Locked for this account: Claude Sonnet 5, GPT-6 Astra, Grok, GPT-5.6 ("not available for this account").
  Claude Haiku 4.5 needs a payment method (AWS Marketplace, not covered by credits): seeded disabled.
- **To verify within 24h:** Cost Explorer shows the Bedrock charges were offset by credits.
- Test: every enabled Bedrock seed model must have a LiteLLM price (keeps the daily spend kill-switch accurate).
- LiteLLM loads the nearest `.env` on import (it found the repo's legacy `.env` with another IAM user's keys);
  `LITELLM_MODE=PRODUCTION` is now set before import.

### Production, ready to switch on (2026-10-11)

- `infra/terraform/database.tf`: with `database = "rds"`, a private RDS Postgres 17 (db.t4g.micro, gp3 20→100 GB,
  encrypted, 7-day backups, deletion protection + final snapshot); `terraform output -raw database_url`.
- `infra/scripts/tf.sh <env> plan|apply|output` keeps staging and production state separate.
  `production.tfvars` exists locally (gitignored). `tf.sh production plan` = 31 resources; staging plan unchanged.
- Deploy workflow: environment is a choice; production uses its own role (`AWS_DEPLOY_ROLE_ARN_PRODUCTION`) and
  never falls back to staging's. Production deploys only by hand.
- **Not applied** (~US$35/month): the founder decides when. Runbook: `infra/README.md` → Production. Upgrade the
  AWS account to the Paid plan first.
- Error reports (Sentry) now carry environment and release (deploy tag) on web, API and worker. Needs the founder's
  Sentry DSNs: `SENTRY_DSN_API` in the server env, `NEXT_PUBLIC_SENTRY_DSN` as a GitHub variable.

### Legal pages (2026-10-11)

- Terms: minimum age 18 (DPDP treats under-18s as children needing verifiable parental consent, which we don't
  collect; matches the Play listing), covers the Android app, jurisdiction city from config.
- Privacy: named service providers and where they process data (AWS Mumbai; Groq/Google/Anthropic/OpenAI, Tavily,
  LiveKit, Deepgram, Sentry in the US; Razorpay), cross-border transfer, cookies, email choices, the Android app,
  retention of logs, full DPDP rights incl. consent withdrawal, nomination and the Data Protection Board, children,
  breach notification. Claims checked against the code (e.g. Sentry scrubbing).
- Business details were never passed into the web build (the live site showed placeholders). The deploy now passes
  `NEXT_PUBLIC_LEGAL_NAME/ADDRESS/CITY`, `NEXT_PUBLIC_SUPPORT_EMAIL/PHONE`, `NEXT_PUBLIC_GRIEVANCE_OFFICER` from
  GitHub repository variables, and the image tag hashes every baked-in value so a change triggers a rebuild.
- Support email default is now `support@provok.in`, but **no mailbox receives it yet** (needs forwarding or a
  mail host + MX records). **Have a lawyer review the pages before launch.**

### Email unsubscribe (2026-10-11)

- Users can turn off debate emails (challenge, your turn, verdict) in Settings → Email; account emails
  (verification, password reset) always send. Column `users.email_notifications` (migration `0003`).
- Every notification email has an "Unsubscribe from debate emails" footer link to `/unsubscribe?token=…`
  (a confirm click, so mail-filter link scanners can't unsubscribe people) and RFC 8058 one-click headers
  (`List-Unsubscribe` → `POST /api/v1/email/unsubscribe?token=…`, `List-Unsubscribe-Post`), which Gmail and Yahoo
  expect. The token is a 1-year JWT of type `unsubscribe`; other token types are rejected. 175 backend tests pass.

## Not yet verified (needs your accounts/keys)

- **Video**: needs LiveKit + Deepgram keys and S3 storage; never exercised against real services.
- **Razorpay**: tested with mocked API + real signature math; do one test-mode purchase before launch.
- **Google sign-in**: needs an OAuth client; flow is standard but untested live.
- **Email**: only the console provider was exercised; set up Resend/SMTP and send a real reset email.
- **Real devices**: automated Chromium (desktop + Pixel 7) passes; still do a manual pass on iOS Safari.

## Decisions (spec ambiguities resolved)

- **Auth/realtime/storage** are first-party (FastAPI + Redis websockets + S3) instead of Supabase.
  "Phone OTP required to debate" → **verified email** required to debate and vote.
- **Video is HvH only** (AI can't appear on camera). A video challenge that falls back to AI becomes a live text debate.
- **Pricing**: a debate costs the flagship price if *any* AI side uses a flagship model. Free AI debates
  cover standard models only (`FREE_DEBATES_COVER_FLAGSHIP`). Accepting an AI fallback consumes a free debate/credits.
- **Vote windows**: live rounds close after 30s; async rounds stay open until the next round ends;
  the closing round has a final window (90s live / 6h async). Votes can be changed while open.
- **Swap test**: run 2 swaps the A/B labels and the order of the claim ledger; the transcript stays
  chronological (FOR always opens).
- **Critic before streaming** (spec v1 choice): draft → critique → optional revision → stream.
- **Judge rotation**: each judging attempt uses one judge for both runs; a retry may rotate to the next
  enabled judge (never mid-verdict).
- **Auto-resume**: debates paused by provider failures retry after 5, 15 and 45 min (up to 3×/day), then wait for an admin.
- **Concession** ends the rounds; the conceding side loses without an LLM verdict.

## Launch checklist

1. **Paid LLM keys.** Free tiers (Groq 8k TPM, Gemini 20 req/day) cannot sustain real traffic.
   Add Anthropic/OpenAI keys; enable models in `/admin → Models`. Fill in the real GPT-6 Astra id or leave it disabled.
2. **Verify model ids** in `model_registry.seed.json` against provider docs (the old `.env`'s Groq id was invalid).
3. Set `DAILY_LLM_SPEND_ALERT_USD` (auto kill-switch) and Sentry DSN.
4. Production env: strong `JWT_SECRET_KEY`, `COOKIE_SECURE=true`, `TRUSTED_PROXY_COUNT`, `CORS_ORIGINS`, `EMAIL_PROVIDER=resend`.
5. **Fresh database**: the schema is new and not compatible with the legacy DB in your current `.env`.
   Point `DATABASE_URL` at a new database and run `python -m backend.app.cli migrate`.
6. Razorpay: live keys, webhook (`payment.captured`, `order.paid`, `payment.failed`), and fill the business
   details (`NEXT_PUBLIC_LEGAL_*`) shown on Terms/Privacy/Refunds/Contact. **Have a lawyer review those pages.**
7. Google OAuth client with redirect `{WEB_URL}/api/v1/auth/google/callback`.
8. Storage bucket (`STORAGE_BACKEND=s3`) and, for video, LiveKit + Deepgram + webhook.
9. Create an admin (`cli create-admin`), seed a few featured debates (`cli seed-featured`).
10. Uptime monitor on `/health/ready`; check the worker heartbeat shows `ok`.
11. Manual QA pass in real browsers (iOS Safari, Android Chrome, desktop).

## Known gaps / next up

- `npm audit` reports advisories in the ESLint toolchain (dev-only, not shipped).
- Push notifications (web push) are not implemented; in-app + email only.
