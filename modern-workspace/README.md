# modern-workspace — the ProxyPal UI

React 19 + Vite. No UI framework, no Tailwind: plain CSS in `src/index.css` with CSS variables for
the themes, and hand-written inline SVG for every icon and provider mark.

| File | Role |
| --- | --- |
| `src/App.jsx` | The whole application — chat, streaming, settings, provider/key/model management, mascot, speech. |
| `src/i18n.js` | Flat AR/EN/FR dictionaries; `dir` and font choices come from the active locale. |
| `src/index.css` | Themes, RTL layout, compact settings sections, animations. |
| `src/fonts.css` | The Arabic font stack offered in settings. |
| `public/avatars/` | The three onboarding avatars. |

```bash
npm install
npm run dev      # http://localhost:5173, expects the gateway on http://127.0.0.1:8790
npm run lint     # oxlint
npm run build    # dist/, copied into the Docker image as the static app
```

`base: './'` in `vite.config.js` keeps the build path-agnostic so it can be served under `/app/`.
Point the dev server at another gateway with `VITE_GATEWAY_URL`.

Conventions: user-visible strings always go through `t()` in all three locales; preferences are
persisted to `localStorage` with a debounce; `GATEWAY_VERSION` here must match `gateway.py`.
