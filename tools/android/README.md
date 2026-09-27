# Hogs & Dogs on Google Play

The game is already an installable web app (PWA). Google Play accepts it as a
Trusted Web Activity (TWA): a small Android app that opens the live site full
screen with no browser bar. Every update you deploy to Vercel shows up in the
Play Store app at once, with no new upload needed.

## Steps

1. **Google Play developer account.** Sign up at https://play.google.com/console
   ($25 one-time fee, ID check).
2. **Build the Android package.** The easy way needs nothing installed:
   - Go to https://www.pwabuilder.com, enter `https://hogs-and-dogs.vercel.app`
     and choose **Package for stores → Android**.
   - Use the values in `twa-manifest.json` in this folder (package ID
     `app.vercel.hogs_and_dogs.twa`, colors, start URL).
   - Download the zip. It has the `.aab` file to upload, a signing key
     (`signing.keystore` plus its passwords) and an `assetlinks.json`.
   - **Keep the signing key and passwords safe and private.** You need the same
     key for every future update. Never commit it to this repository.
   - Or with Bubblewrap on your own computer:
     `npx @bubblewrap/cli init --manifest https://hogs-and-dogs.vercel.app/manifest.webmanifest`
     then `npx @bubblewrap/cli build`.
3. **Prove you own the site.** Copy the SHA-256 fingerprint of your signing
   key (PWABuilder puts it in `assetlinks.json`; Play Console also shows the
   "App signing key" fingerprint under *Setup → App signing*; use that one).
   Put it into `assetlinks.template.json`, save it as
   `.well-known/assetlinks.json` in the repo root, and deploy. Without it the
   app still works but shows a browser bar at the top.
4. **Store listing.** In Play Console create the app, then upload the `.aab`
   under *Testing → Internal testing* first. Fill in the listing:
   - short and full description, the 512×512 icon (`assets/app/icon-512.png`),
     a 1024×500 feature graphic, and at least 2 phone screenshots;
   - content rating questionnaire (hunting with dogs: answer the violence
     questions honestly; it is cartoon animal hunting, no blood);
   - privacy policy URL (needed because players can sign in);
   - Data safety form: account name and game save (for cloud save), analytics
     events.
5. **Testing.** New personal developer accounts must run a closed test with at
   least 12 testers for 14 days before going to production.
6. **Publish** to production.

## Apple App Store

Apple does not accept plain website wrappers, so the iPhone version needs a
native shell (for example Capacitor) with some native features, a Mac with
Xcode, and a $99/year Apple developer account. Until then iPhone players can
use Safari → Share → **Add to Home Screen**, which installs the game like an
app.
