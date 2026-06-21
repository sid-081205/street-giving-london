# Gamifying Homelessness

Accompanies my substack piece: https://sid081205.substack.com/p/gamifying-homelessness

A data-science project asking: where in central London should a homeless person position themselves to maximise their chance of getting off the street? It models an hourly "giving opportunity" surface (`lambda`) across London's LSOAs from real footfall, crowd mix, giving behaviour, weather mood, competition, and food access.

- **Analysis:** [`analysis.ipynb`](analysis.ipynb) — the full model, from prepared data
  to figures.
- **Interactive map:** [`deploy/`](deploy/) — `index.html` + `data.js`, live at
  https://deploy-mocha-pi-53.vercel.app
