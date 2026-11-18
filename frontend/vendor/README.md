# Vendored files

Third-party files the frontend loads, pinned and committed so the page makes no CDN request. To upgrade one, download the new version under a new versioned name, update the reference in `index.html` or `styles.css`, and replace its row here.

| File | Version | Source | Licence | sha256 |
|---|---|---|---|---|
| `d3-7.9.0.min.js` | 7.9.0 | https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js | ISC, `d3-7.9.0.LICENSE.txt` | `f2094bbf6141b359722c4fe454eb6c4b0f0e42cc10cc7af921fc158fceb86539` |
| `d3-7.9.0.LICENSE.txt` | 7.9.0 | https://cdn.jsdelivr.net/npm/d3@7.9.0/LICENSE | | `3e6849627f74ff73c257a3ae1efb574015d94fc1035c05ec3c15805165efcbc4` |
| `topojson-client-3.1.0.min.js` | 3.1.0 | https://cdn.jsdelivr.net/npm/topojson-client@3.1.0/dist/topojson-client.min.js | ISC, `topojson-client-3.1.0.LICENSE.txt` | `25cd02ae486cc5063e0215a4e4cfb15de83700c87ac48bac4d57dc6aaf3ebb89` |
| `topojson-client-3.1.0.LICENSE.txt` | 3.1.0 | https://cdn.jsdelivr.net/npm/topojson-client@3.1.0/LICENSE | | `4c4d15b635e04e691825a76db7d33f7f2033b55669a7430011694f31e6c65999` |
| `atkinson-hyperlegible-next-5.3.0-latin-wght.woff2` | Fontsource 5.3.0 | https://cdn.jsdelivr.net/npm/@fontsource-variable/atkinson-hyperlegible-next@5.3.0/files/atkinson-hyperlegible-next-latin-wght-normal.woff2 | OFL 1.1, `atkinson-hyperlegible-next-5.3.0.OFL.txt` | `18b2a1a39a2fa298b0ba5390aca68462669826c90925656f1c1f6796e0e1bbaf` |
| `atkinson-hyperlegible-next-5.3.0-latin-ext-wght.woff2` | Fontsource 5.3.0 | https://cdn.jsdelivr.net/npm/@fontsource-variable/atkinson-hyperlegible-next@5.3.0/files/atkinson-hyperlegible-next-latin-ext-wght-normal.woff2 | OFL 1.1, `atkinson-hyperlegible-next-5.3.0.OFL.txt` | `7dae0c6c66af1aec82e096186aeb1f0e6fa36ab8061ed65422f2b7daf4dd93f3` |
| `atkinson-hyperlegible-next-5.3.0.OFL.txt` | Fontsource 5.3.0 | https://cdn.jsdelivr.net/npm/@fontsource-variable/atkinson-hyperlegible-next@5.3.0/LICENSE | | `474a034e99845062f661855caaa505880d0e9009deddc2727a92795eab374955` |
| `../data/world-110m.json` | sane-topojson as published by Plotly | https://cdn.plot.ly/world_110m.json | MIT, `../data/world-110m.LICENSE.txt` | `d75915eaa31c870df6b972c9e5bb86910197825f33dcfef740f3b2f68cffe843` |
| `../data/world-110m.LICENSE.txt` | | https://raw.githubusercontent.com/etpinard/sane-topojson/master/LICENSE | | `ce913ee8d2f3622699fe9c40c952b59ce6d82ecfb4195c884e9b182f117e86c9` |

`world-110m.json` is Natural Earth 1:110m geometry; its `countries` object uses ISO 3166-1 alpha-3 ids, the same codes as the registry.
