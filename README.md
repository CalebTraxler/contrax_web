# Contrax

Marketing site for Contrax — check any contractor quote against local permit records, license boards, and real prices, then send a ready-made counter-offer.

Pure static HTML/CSS/JS. No framework, no build step, no dependencies.

## Run locally

```sh
python3 -m http.server 8080
# open http://localhost:8080
```

(Or open `index.html` directly — everything works from the filesystem except clipboard copy, which needs a secure context.)

## Deploy

Any static host works as-is:

- **GitHub Pages**: repo Settings → Pages → deploy from `main`, root.
- **Vercel / Netlify / Cloudflare Pages**: import the repo, no build command, output dir `/`.

## Configuration & secrets

Real endpoints and keys live in `js/config.js`, which is **gitignored**. To wire up the waitlist form:

```sh
cp js/config.example.js js/config.js
```

Then set `WAITLIST_ENDPOINT` to a Formspree/Buttondown URL or your own API. Until it's set, the form still shows success but only logs a console warning and stores emails in the visitor's localStorage (i.e., not persisted anywhere useful) — don't launch without configuring it.

Never commit `js/config.js` or any `.env` file.

## Structure

```
index.html            single-page site (hero, how it works, sample report,
                      data/map, family plan, pricing, FAQ, waitlist)
css/style.css         design system + animations (respects prefers-reduced-motion)
js/main.js            nav, scroll reveals, copy button, waitlist form
js/config.example.js  template for local config
```

## Notes

- Example prices and report contents on the page are illustrative.
- Fonts (Fraunces, Inter) load from Google Fonts; everything else is self-contained.
