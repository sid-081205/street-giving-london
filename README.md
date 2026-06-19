# Street-Giving Lambda Analysis

This repo has one cleaned workflow:

1. `prepare_data.py` fetches and caches real input data in `data/processed/`.
2. `analysis.ipynb` reads those prepared files and calculates hourly lambda.
3. `site/index.html` reads `outputs/analysis/web/data.js` and visualizes the result.

## Model

```text
lambda(l, t) = gross_giving(l, t) * competition_factor(borough)
```

The only hardcoded behavioural inputs are the base giving probabilities:

```text
workers 0.010, leisure 0.030, shoppers 0.012,
tourists 0.020, events 0.030, students 0.045
```

Everything else is calculated from prepared data:

- TfL station footfall and RODS hourly profiles for hourly flow.
- TfL station coordinates for spreading flow to LSOAs.
- BRES employment and ASHE pay for worker income.
- Geofabrik/OpenStreetMap POIs for leisure, shopping, tourism, events, and students.
- MHCLG rough-sleeping counts for borough competition pressure.

## Run

Use the repo venv/kernel:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt ipykernel
.venv/bin/python -m ipykernel install --user --name street-giving-london --display-name "Python (street-giving-london)"
```

Prepare data:

```bash
.venv/bin/python prepare_data.py
```

Then run `analysis.ipynb` with the `Python (street-giving-london)` kernel.

Open the map:

```text
site/index.html
```

## Outputs

- `outputs/analysis/hourly_lambda.csv`
- `outputs/analysis/lambda_surface.gpkg`
- `outputs/analysis/web/lambda_surface.geojson`
- `outputs/analysis/web/data.js`
