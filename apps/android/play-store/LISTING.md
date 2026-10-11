# Play Store listing: Provok

Draft answers for Play Console. Check every answer against how the app actually behaves at submission time.

## Store listing

- **App name** (30): `Provok: Debate Humans & AI`
- **Short description** (80): `Pick a side, argue it, and let the crowd and an AI judge decide who won.`
- **App icon**: `icon-512.png` · **Feature graphic**: `feature-graphic-1024x500.png`
- **Phone screenshots**: 2–8, portrait, from the staging app (home feed, a live debate, the verdict).
- **Category**: Entertainment (alternative: Education) · **Contact email**: the support address on /contact
- **Privacy policy**: https://provok.in/privacy

**Full description** (4000):

```
Ask anything. Pick your corners. Argue it out.

Provok is the arena for ideas. Pose a question, choose who argues each side, and let the audience and an
impartial AI judge decide who made the stronger case.

DEBATE ANYONE
• Challenge a friend with a private invite link, or take an open challenge from the community
• Debate an AI that researches, plans and argues back
• Watch AI models debate each other, and see which one argues better

A REAL FORMAT
Every debate runs Opening, Rebuttal, Cross-examination and Closing. Turns are timed: minutes for live debates,
up to a day for async ones you play at your own pace.

THE CROWD AND THE JUDGE
The audience votes after every round. The tally stays hidden until the round closes, so nobody piles on.
At the end, an AI judge checks the claims and citations and explains its verdict, shown separately from the
crowd's vote.

FACE TO FACE
Go live on video and argue in real time. Your speech is transcribed into the debate record.

FAIR AND SAFE
Topics that tend to turn into fights, like politics and religion, are off the table. Reports are reviewed, and
the judge cannot be talked into a result.

Human vs human debates are free. Your first AI debates are free too.
```

## App content

- **Ads**: No.
- **App access**: sign-in needed for debating and voting; watching is open. Give reviewers a test account
  (email + password) with a verified email.
- **Content rating** (IARC questionnaire): category *Social / Communication*; users interact and share
  user-generated content: **Yes**; moderation and reporting exist (report button, admin review); no violence,
  sexual content, gambling or drugs in the app itself.
- **Target audience**: 18 and over. Keeps the app outside the Families policy; matches DPDP consent rules for
  minors.
- **AI-generated content**: the app generates text with AI. It has an in-app way to report offensive output
  (the report button on turns), which Play requires.
- **Financial features**: none (credits are an in-app virtual item; see payments note below).
- **Account deletion**: in the app (Settings → Delete account). Web link for the form:
  https://provok.in/settings (sign-in required) and the privacy policy section on deletion.

## Data safety

Collected (all **encrypted in transit**; users can **request deletion**, done in Settings):

| Data type | Collected | Shared | Why |
|---|---|---|---|
| Email address | Yes, required | No | Account, sign-in, account emails |
| Name (display name, username) | Yes, required | No | Profile shown on debates |
| User IDs | Yes | No | Account |
| Photos | Optional (avatar) | No | Profile |
| Other user-generated content (debate text, votes) | Yes | No* | App functionality |
| Voice or sound recordings | Optional (video debates) | No* | Live transcription into the debate |
| Videos | Optional (video debates) | No | Live debate; recording only if enabled |
| Purchase history | Yes (credit packs) | No | Wallet and refunds |
| App interactions, crash logs, diagnostics | Yes | No | Analytics, error reporting (Sentry) |

\* Debate text goes to AI model providers and speech goes to a transcription provider **to provide the feature on
our behalf**. Play counts processing by service providers as *not sharing*, but name them in the privacy policy.

Not collected by the app: payment card or UPI details (handled by Razorpay's checkout), precise location, contacts.

## Payments note

Credit packs are digital goods sold through Razorpay on the website. Inside a Play-distributed app, Google Play's
payments policy generally requires Google Play Billing for digital goods (India allows user-choice billing for
some developers). **Decide before submitting**: hide purchases in the Play build, or integrate Play Billing. Human
vs human and watching stay free either way.
