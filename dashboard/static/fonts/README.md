# Vendored fonts

The dashboard must run on an air-gapped machine (see `docs/architecture.md`), so
it may not fetch fonts from a CDN. These files are served from this repo and
declared as `@font-face` in `../css/base.css`.

| File | Family | Weight |
|------|--------|--------|
| `inter-400.woff2` | Inter | 400 |
| `inter-500.woff2` | Inter | 500 |
| `inter-600.woff2` | Inter | 600 |
| `geist-mono-400.woff2` | Geist Mono | 400 |
| `geist-mono-500.woff2` | Geist Mono | 500 |

Latin subset only (`U+0000-00FF` and friends) — the UI is English, and the full
set is several times the size for glyphs nothing renders.

Both families are licensed under the SIL Open Font License 1.1, which permits
redistribution alongside this project:

- Inter — <https://github.com/rsms/inter>
- Geist Mono — <https://github.com/vercel/geist-font>

## Replacing them

Weights come from the Google Fonts latin subset. To refresh, take the `latin`
`@font-face` block for each weight from
`https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Geist+Mono:wght@400;500`
(request it with a browser User-Agent to be served woff2), download the `.woff2`
each one points at, and keep the file names above.
