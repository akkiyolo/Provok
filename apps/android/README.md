# Provok for Android

A **Trusted Web Activity** (TWA): the app opens the Provok website full-screen in Chrome, with no URL bar. Every web
feature (Google sign-in, debates, video, Razorpay) works unchanged, and a web deploy updates the app without a Play
release. Only icon, name or package changes need a new upload.

| Build | Package | Opens |
|---|---|---|
| `staging` | `in.provok.app.staging` | https://staging.provok.in |
| `production` | `in.provok.app` | https://provok.in |

The package name is permanent once the app is on Play.

## How the app and the site trust each other

Android shows the site without a URL bar only if both sides agree (Digital Asset Links):

- The app declares the site: `@string/asset_statements`, generated per flavour in `app/build.gradle.kts`.
- The site declares the app: `GET /.well-known/assetlinks.json`, served by the API from the server env
  `ANDROID_PACKAGE` and `ANDROID_CERT_SHA256` (comma-separated fingerprints).

If they don't match, the app still works but shows a URL bar. Check a live site with
`curl https://staging.provok.in/.well-known/assetlinks.json`.

## Building

Needs JDK 17+ and the Android SDK (`local.properties`: `sdk.dir=...`). Android Studio provides both.

```bash
cd apps/android
./gradlew assembleStagingRelease      # app/build/outputs/apk/staging/release/*.apk  (install on a phone)
./gradlew bundleProductionRelease     # app/build/outputs/bundle/productionRelease/*.aab  (upload to Play)
./gradlew bundleProductionRelease -PversionCode=2 -PversionName=1.0.1   # every Play upload needs a new versionCode
```

Release builds are signed with the **upload key** from `keystore.properties` (gitignored):

```properties
storeFile=../provok-upload.jks
storePassword=...
keyAlias=upload
keyPassword=...
```

**Back up `provok-upload.jks` and `keystore.properties`** to a password manager or private cloud folder. With Play
App Signing (the default) a lost upload key can be reset through Play support, but that takes days.

Icons and store graphics: `python tools/make_icons.py app/src/main/res play-store`.

## Releasing on Google Play

1. **Developer account** (one-time US$25, identity verification): https://play.google.com/console/signup.
   New *personal* accounts must run a **closed test with at least 12 testers for 14 days** before they can publish
   to everyone. An *organisation* account (needs a D-U-N-S number) skips this.
2. **Create the app** → upload `Provok-<version>.aab` to a testing track. Play App Signing is on by default.
3. **Add Play's signing key to the site.** Play Console → *Test and release → App integrity → App signing* shows the
   "App signing key certificate" SHA-256. Append it to `ANDROID_CERT_SHA256` (keep the upload key's too), push the
   env and deploy. Without this, installs from Play show a URL bar.
4. Fill in the store listing, content rating, data safety and target audience: answers are in
   [`play-store/LISTING.md`](play-store/LISTING.md).

Production (`provok.in`) needs `ANDROID_PACKAGE=in.provok.app` and the fingerprints in the production server env.
