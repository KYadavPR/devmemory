# Bundled fonts

The dashboard ships three typefaces as WOFF2 (latin subsets) under
`web/static/assets/`, so it renders correctly with no network access. All three
are licensed under the **SIL Open Font License 1.1**, which permits bundling and
redistribution with this software.

| Family | Files | Copyright | License |
|---|---|---|---|
| Newsreader | `newsreader-var-*.woff2` | Copyright 2019 The Newsreader Project Authors (https://github.com/productiontype/Newsreader) | OFL-1.1 |
| IBM Plex Sans | `plexsans-var-*.woff2` | Copyright 2017 IBM Corp. (https://github.com/IBM/plex) | OFL-1.1 |
| IBM Plex Mono | `plexmono-{400,500,600}-*.woff2` | Copyright 2017 IBM Corp. (https://github.com/IBM/plex) | OFL-1.1 |

Full licence text: https://openfontlicense.org/open-font-license-official-text/

The OFL requires that the fonts not be sold on their own, that the licence
travel with them, and that any *modified* version be renamed. DevMemory
redistributes them unmodified apart from subsetting to the latin range, so no
Reserved Font Name restriction is triggered.

The `@font-face` declarations live in
`web/frontend/src/theme/fonts.css`; the source files are in
`web/frontend/src/theme/fonts/` and Vite hashes them into `web/static/assets/`
at build time.
