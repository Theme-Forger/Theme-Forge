# Free asset sources — API reachability and license terms

## Refreshed
Date: 2026-09-09. Sources consulted: 4 parallel research passes, all endpoints probed live.

## Changed since last refresh
- First creation of this domain. Verification-only pass; nothing built against it yet.
- **unDraw's documented API is dead** (`/api/illustrations` → 404) but an undocumented keyless
  endpoint is live: `undraw.co/api/search?q=<term>` → 200 JSON with `cdn.undraw.co` SVG URLs.
- **DrawKit is NOT MIT-licensed** despite Product Hunt and aggregator sites saying so. Its own
  license page is a custom proprietary grant with an anti-redistribution clause.
- **LottieFiles has no official content API.** Staff statement: *"We currently don't offer an API
  for searching and downloading free animations."* An undocumented GraphQL endpoint at
  `graphql.lottiefiles.com` is live and ungated, but their ToS forbid automated access.
- **Poly Haven's API is real** (`api.polyhaven.com`, no key) — but `polyhaven.com/api` is a 404;
  the docs live at `/our-api`.
- **Boring Avatars' hosted API is retired** — `source.boringavatars.com` is dead; npm library only.

---

## The two traps that decide viability

Neither is about whether an API exists. Both are about what happens after you ship.

### Trap 1 — an asset's license and its API's terms are different documents

Several sources whose *assets* need no attribution attach attribution to *API use*:

| Source | Asset license says | API terms say |
|---|---|---|
| Poly Haven | CC0 — *"You do not need to give credit"* | ToS §2.5: surfacing content via the live API requires a *"'Powered by Poly Haven' credit displayed near the content"*, and §2.4 requires a unique `Referer`/User-Agent |
| Coverr | *"commercial and non-commercial purposes at no cost"*, credit optional | *"If you make use of the Coverr API, you'd have to show your users where the videos are pulled from... include our logo and make it clickable"* |
| Pixabay | Content License — attribution not required | terms require caching 24 h and showing users the image source when displaying search results |

**Consequence:** "no attribution required" cannot be read off the license page alone. A default-
attribution-free run must check the *API terms* too — or avoid live API calls and rely on the
asset license by vendoring CC0 files at build time, which is the cleaner escape.

### Trap 2 — redistribution, not attribution, is the binding constraint

Theme Forge **exports theme zips**. Most free-asset licenses permit use inside your own project
but forbid redistributing the assets as a compilation or pack. That is disqualifying regardless
of attribution:

| Source | Operative restriction |
|---|---|
| unDraw | grant *"does not include the right to compile assets... to replicate a similar or competing service"*; forbids distributing in packs and *"scraping/downloading without consent"*; **explicitly prohibits use "for training, fine-tuning, or developing artificial intelligence, machine learning models"** |
| DrawKit | *"may not sell, distribute, lease, license, sub-license or offer icon and illustration files to any third party"*; no redistribution *"on a stand-alone basis or as a compilation"* |
| Blush / Doodle Ipsum | modification and commercial use allowed, but forbids re-selling/re-distributing and compiling to replicate a competing service |
| LottieFiles | redistribution *is* granted, but **share-alike**: *"Modifications... are deemed derivative works and must also be expressly distributed under the same terms"* — the licence infects an exported theme. Also no compiling to build a competing service |
| Mixkit | prohibits scripted mass download, aggregation *"on a stock or inventory basis"*, and **explicitly forbids hotlinking/framing/linking** |
| Coverr | *"can't be resold or offered as part of services to which providing videos can help"*; signed URLs are key-bound |

unDraw's AI/ML clause deserves separate weight: Theme Forge is an AI-driven generator, so that
clause points directly away from this use case. Treat as legal-review-pending, not a quick win.

**The safe set for a tool that redistributes is therefore CC0 / MIT / OFL only.**

---

## Verification table

`API` = public HTTP API returning downloadable asset URLs. `PSEUDO` = static raw-file or CDN URL
pattern, not an API. `BULK` = download/zip/npm only. `NONE` = no programmatic access.

| Source | API | Key | License | Attrib | Rate limit | Hotlink | Adaptable | Verdict |
|---|---|---|---|---|---|---|---|---|
| **Iconify** | API `api.iconify.design` | no | API MIT; per-set varies | per-set | undocumented | yes | yes, `?color=` | **USABLE** — self-hostable |
| **DiceBear** | API `api.dicebear.com` | no | code MIT; per-style varies | per-style | undocumented | yes | yes, seeded | **USABLE** — filter to CC0/MIT |
| **Pexels** (photo+video) | API `api.pexels.com` | yes | Pexels License | no | 200/hr, 20k/mo | yes | no (raster) | **USABLE** |
| Open Peeps | via DiceBear | no | **CC0** | no | via DiceBear | yes | yes (SVG) | **USABLE via DiceBear** |
| unDraw | API (undocumented) | no | custom | no | undocumented | `<img>` only, no CORS | yes, 1 accent | **LEGAL BLOCK** (Trap 2 + AI clause) |
| Humaaans | BULK (Gumroad zip) | no | CC0 | no | n/a | self-host | yes (SVG) | BULK_VENDOR_ONLY |
| DrawKit | NONE | acct | custom, **not MIT** | no | n/a | self-host | yes | BULK, anti-compilation |
| Blush | NONE (see Doodle Ipsum) | acct | per-artist, freemium | no | n/a | self-host | in-app only | NONE |
| Kenney | BULK | no | CC0 | no | n/a | self-host | raster sprites | BULK — poor recolor fit |
| Quaternius | BULK (Drive/itch) | no | CC0 | no | n/a | self-host | 3D meshes | BULK — out of scope |
| **LottieFiles** | **EMBED-ONLY** officially | no | Lottie Simple License | no | undocumented | yes | yes (JSON) | **share-alike + ToS-adverse** |
| **Poly Haven** | API `api.polyhaven.com` | no | **CC0** assets | no*/API yes | none documented | unstated | yes | **USABLE, textures only** |
| ambientCG | API v3 | no | **CC0** | no | none documented | tolerated | yes | reachable, **wrong payload** |
| Coverr | API `api.coverr.co` | yes | Coverr free | **yes** (API) | 50/hr free | yes | no | opt-in only |
| Mixkit | NONE | no | Mixkit Free | no | n/a | **forbidden** | n/a | **NONE — do not build for** |

### Payload reality check

The gallery is a **self-contained offline HTML file**. Reachability is not sufficiency:

| Source | Smallest usable unit |
|---|---|
| Poly Haven textures | 1k JPG **per-map** files, 150–650 KB; CDN thumbs `?width=256` a few KB |
| Poly Haven HDRIs | 1.73 MB floor (1k `.hdr`), 389 MB at 16k — and browsers need a Three.js loader |
| ambientCG | **ZIP bundles only**, 5–10 MB minimum, no per-map fetch — must unpack server-side |
| Coverr | 360p 800 KB / 720p 4.0 MB / 1080p 7.2 MB |
| LottieFiles | 6.7–62 KB JSON — the only source that is structurally *ideal* |
| DiceBear / Iconify | single-digit KB SVG |

ambientCG is the "reachable and still useless" case: Poly Haven's per-map endpoints strictly
dominate it for web use.

---

## Tier verdicts

**Icons — solved.** Iconify (~250k icons, 200+ sets, keyless, self-hostable, MIT API) plus
Simple Icons for brand marks (already aggregated by Iconify). Nothing further needed.

**Avatars — solved.** DiceBear, keyless, deterministic from seed, self-hostable via
`@dicebear/collection` npm. Filter to CC0/MIT styles. Open Peeps arrives free through it.
`ui-avatars.com` is the only initials-with-theme-colour option if that shape is ever wanted.

**Photos and video — solved, with zero new vendors.** `api.pexels.com/videos/search` uses the
**same key already held** and returns `video_files[]` direct links plus `video_pictures[]`
posters. 200/hr, 20k/mo, no attribution legally required. This strictly dominates Coverr
(attribution-required) and Mixkit (unusable). Pixabay video is a keyed backup.

**Illustrations — no automatable attribution-free source that permits redistribution.**
The original hypothesis is confirmed, and for a stronger reason than "no API": the two sources
that *do* have working APIs (unDraw, Doodle Ipsum/Blush) both forbid compiling or redistributing
assets, and unDraw additionally forbids AI/ML use. The CC0 sets (Humaaans, Open Peeps) are
redistributable but have no API of their own. **Theme Forge's generated geometric illustrations
stay.** The one genuine option is Pixabay's `image_type=vector|illustration` (key, 100 req/min,
no attribution) — a real find, since this tier was assumed empty.

**Geometric patterns / backgrounds — effectively no API.** This was the highest-hoped-for tier
and it is the emptiest. Every generator in the space (fffuel, Haikei, BGJar, SVGBackgrounds,
coolbackgrounds, 10015) is browser-only with no HTTP API; Pattern Monster's `/api/patterns`
returns 404. Only two reachable options: **PHP-Noise** (`php-noise.com/noise.php`, keyless,
`&json&base64` inlines a 6.7 KB PNG, fully parameterised) and **Hero Patterns**, which is
**CC BY 4.0 — attribution required** and only reachable as a pseudo-API via npm/jsDelivr
mirrors. Pattern Monster (MIT) is vendorable as data and rendered client-side — zero bytes over
the wire, infinitely recolorable, offline-native, and the best structural fit found anywhere.

**Fonts — the cleanest win, and it solves an existing problem.** `api.fontsource.org/v1/fonts`
is keyless, covers 2000+ families (superset of Google Fonts), exposes a **machine-readable
per-font `license` field** (e.g. Inter → `"OFL-1.1"`), and — critically — returns **TTF** URLs,
not just WOFF2. `tf_outline.py` needs TTF and cannot parse WOFF2, and React Native needs TTF
too, so this replaces the ad-hoc `fonts.gstatic.com` fetch with a licensed, queryable catalogue.
Bunny Fonts is a GDPR-clean CSS-only alternative with no metadata endpoint.

**3D — out of scope.** Poly Haven and Quaternius are CC0 and real, but a CSS/React-Native theme
generator has no pipeline for meshes, and HDRIs cannot render without a WebGL runtime.

---

## Other reachable APIs worth knowing

Verified live 2026-09-09 unless noted.

- **placehold.co** — keyless, **SVG is the default format**, 396 B for 300×200, colours/text/size
  as URL params. Sub-1 KB inlineable placeholders. No formal license published — small risk.
- **picsum.photos** — keyless, deterministic by seed, no attribution. Already Theme Forge's
  no-key imagery fallback; keep.
- **Art Institute of Chicago** — `api.artic.edu`, keyless, CC0 with an `is_public_domain` filter,
  IIIF lets you request a narrow width so 20–80 KB is achievable. Good source of textile and
  ornament imagery for texture derivation.
- **Met Museum** — keyless, CC0, but no field filtering and a 3.4 MB ID list per search. ARTIC
  is strictly better ergonomics.
- **QuickChart** — `quickchart.io/chart?format=svg`, AGPL and **self-hostable**, colours fully
  controllable via Chart.js config. Relevant for themed webapp-surface charts.
- **goQR** — `api.qrserver.com`, keyless, `format=svg` + `color=R-G-B`, free commercial, no
  attribution. Narrow but fully theme-recolorable; only useful for a mobile-surface mock.
- **api.color.pizza** and **thecolorapi.com** — keyless colour naming and scheme generation.
  Directly useful for human-readable token names. Note `api.thecolorapi.com` does not resolve;
  use `www.`.
- **Openverse** — real REST API with a `license=cc0` filter, but anonymous limits are **5 req/hr
  and 100/day**, which cannot serve a six-theme run. Needs a registered OAuth client to be viable.

## Checked and rejected — do not re-investigate

- **Pattern Monster API** — `/api/patterns` 404. Client-side only. (The MIT *data* is vendorable.)
- **fffuel, Haikei, BGJar, SVGBackgrounds, coolbackgrounds, 10015, transparenttextures** — all
  browser-only generators, no HTTP API. This is the honest state of the pattern tier.
- **Unsplash** — attribution mandatory and enforced by API terms; must hotlink AND fire a
  download-tracking endpoint; `source.unsplash.com` retired.
- **Flaticon, Iconfinder, Noun Project** — key required, metered free tier, attribution mandatory.
- **Lordicon** — `cdn.lordicon.com/{id}.json` works but 64.9 KB per Lottie and free use requires
  a backlink.
- **SVGL** (`api.svgl.app`) — works, 130 KB catalogue, but brand/trademark logos only; no use for
  theme differentiation.
- **IconScout** — the vendor LottieFiles points API-seekers to; subscription-gated.
- **Sketchfab Download API** — OAuth per end user; not viable unattended.
- **Poly Pizza** — ~7000 CC0/CC-BY GLB models but requires an account key, and mixed CC-BY means
  per-asset attribution tracking.
- **Boring Avatars hosted API** — retired, `404`/dead. npm library only.
- **Multiavatar, api.adorable.io, joeschmoe.io, placekitten, placeimg, via.placeholder** — dead.
- **SVGMaker, svgapi.com, imagin.studio** — key-walled.
- **RoboHash** — works and keyless, but MIT code with **mixed-license sprite sets (some CC-BY)**.
- **Animate.css, Uiverse.io, useAnimations** — MIT and offline-friendly, but no API; vendor only.
- **No free Lottie registry with a keyless API exists.** SVGator, IconScout, useAnimations are
  all key-walled or paid. This tier is empty apart from LottieFiles' unsanctioned endpoint.

## Implemented in `tf_assets.py`

Built 2026-09-09 against the confirmed set only:

| Tier | Source | Mechanism |
|---|---|---|
| font | Fontsource | keyless; per-font `license` field gated; **TTF** fetched |
| pattern | generated locally | 6 tileable SVGs from theme tokens, no network |
| video | Pexels | existing `PEXELS_API_KEY`; smallest file ≥360px |
| texture | Poly Haven | keyless; `Diffuse` 1k JPG only; vendored, never hotlinked |
| avatar | DiceBear (`tf_avatars.py`) | pinned `9.x`; six CC0 slot styles; CC-BY opt-in; 4 styles blocked |

License policy is three-tier: `attribution_free` (CC0, Pexels) owes nothing; `notice_only`
(MIT, OFL, Apache) ships license text but no visible credit and is allowed by default;
`attribution_req` (CC-BY) is opt-in and is the only tier that populates `licensing.notices`.
Unknown licenses and all share-alike terms are refused outright — share-alike even under
`--allow-attribution`, since it would infect the exported theme.

## Network reality on the deployment host

**Verified 2026-09-09: this organisation blocks media CDNs while permitting API hosts.** The two
are different domains, so a source can look perfectly healthy and still deliver nothing:

| Host | Role | Status here |
|---|---|---|
| `api.polyhaven.com` | metadata | reachable |
| `dl.polyhaven.org` | asset download | **blocked** |
| `api.pexels.com` | search | reachable |
| `videos.pexels.com` | video download | **blocked** |
| `api.fontsource.org` + `cdn.jsdelivr.net` | metadata + font files | reachable |

Consequence on this network: only Fontsource and locally generated patterns produce assets. That
is a clean degradation — `tf_assets.py` names the blocked host and the run continues — but do not
read an empty video/texture tier here as a bug in the fetcher. A blocked host **blackholes**
rather than refuses, so each attempt burns the full timeout; this is why the fetchers cap
candidates and break on an unreachable streak.

## Gaps

- **Rate limits are undocumented for Iconify, DiceBear, unDraw, Poly Haven, ambientCG and the
  LottieFiles GraphQL endpoint.** None publish figures. Self-hosting Iconify/DiceBear sidesteps
  the question entirely and is the recommended posture.
- **Poly Haven's hotlinking stance is unconfirmed by omission** — not permitted in writing, not
  forbidden, across ToS, license page, FAQ and their infrastructure blog post. Moot if assets are
  downloaded and embedded.
- **Blush's full license restrictions could not be read** — `blush.design/license` returned HTTP
  403 to automated fetch. The permissive grant wording is confirmed; the restriction list is not.
- **Humaaans' CC0 claim has no primary-source LICENSE file** — asserted on distribution pages only.
- **placehold.co publishes no formal license or terms.**
- **Pixel Encounter** (`pixelencounter.com/api/v1/svg/random`) could not be confirmed live —
  probes returned `000` and WebFetch failed certificate validation. Do not adopt without an
  independent check.
- **Kenney's and Quaternius' own sites were unreachable** from the research network (corporate
  filter); their CC0 terms were confirmed from secondary sources including Kenney's own posts.
- **Pixabay reachability unverified** (sandbox DNS block); terms confirmed from official docs.

## Sources

All accessed 2026-09-09.

- [undraw.co/license](https://undraw.co/license) · [undraw.co/api/search](https://undraw.co/api/search?q=team)
- [humaaans.com](https://www.humaaans.com/) · [openpeeps.com](https://www.openpeeps.com/)
- [dicebear.com/introduction](https://www.dicebear.com/introduction/) · [dicebear.com/styles/open-peeps](https://www.dicebear.com/styles/open-peeps/)
- [blush.design/plans](https://blush.design/plans) · [blush.design/license](https://blush.design/license) (403 to automated fetch)
- [drawkit.com/license](https://www.drawkit.com/license) · [kenney.nl/support](https://kenney.nl/support) · [quaternius.com](https://quaternius.com/)
- [iconify.design/docs/api](https://iconify.design/docs/api/) · [github.com/iconify/api](https://github.com/iconify/api)
- [developers.lottiefiles.com](https://developers.lottiefiles.com/) · [forum.lottiefiles.com — free animations via API](https://forum.lottiefiles.com/t/free-animations-via-api/8367) · [lottiefiles.com/page/license](https://lottiefiles.com/page/license)
- [polyhaven.com/our-api](https://polyhaven.com/our-api) · [Poly-Haven/Public-API ToS](https://github.com/Poly-Haven/Public-API/blob/master/ToS.md) · [polyhaven.com/license](https://polyhaven.com/license)
- [docs.ambientcg.com/api/v3](https://docs.ambientcg.com/api/v3/) · [docs.ambientcg.com/license](https://docs.ambientcg.com/license/)
- [coverr.co/developers](https://coverr.co/developers) · [coverr.co/license](https://coverr.co/license)
- [mixkit.co/terms](https://mixkit.co/terms/)
- [pexels.com/api/documentation](https://www.pexels.com/api/documentation/) · [pixabay.com/api/docs](https://pixabay.com/api/docs/)
- [fontsource.org/docs/api/font-id](https://fontsource.org/docs/api/font-id) · [bunny.net/fonts](https://bunny.net/fonts/)
- [php-noise.com](https://php-noise.com/) · [heropatterns.com](https://heropatterns.com/) · [Pattern Monster source](https://github.com/catchspider2002/svelte-svg-patterns) · [fffuel.co](https://www.fffuel.co/)
- [placehold.co](https://placehold.co/) · [api.artic.edu](https://api.artic.edu/api/v1/artworks) · [quickchart.io](https://quickchart.io/) · [docs.openverse.org](https://docs.openverse.org/)
- [poly.pizza/docs/api/v1.1](https://poly.pizza/docs/api/v1.1) · [sketchfab.com/developers/download-api](https://sketchfab.com/developers/download-api)
