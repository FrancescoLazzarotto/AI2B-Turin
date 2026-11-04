# Welfare Compass — Social Impact Planner for Turin

Welfare Compass helps foundations, third-sector organisations and public institutions decide where in Turin
their funds generate the greatest social impact. For each of the city's 92 statistical zones it measures
demographic isolation, service gaps and socio-economic fragility from open data, matches those needs with the
profile of a specific organisation, and returns a ranked, explainable plan: where to invest, why, how much,
and with which intervention.

The project was built by team **Attention Is All We Need** for the Turin stage of the
**Campionato Universitario AI** organised by [AI2B](https://ai2b.games) on 4 November 2026, Track 3 *Welfare*
(active ageing, labour inclusion, urban fragility).

## Highlights

- **Data-driven needs.** Factor weights inside each index come from a principal component analysis over the
  92 zones, not from hand-picked coefficients.
- **AI that reads people, a formula that decides.** A local LLM turns a free-text description of the
  organisation into a structured profile, writes the plan and answers questions about it; the ranking itself
  is a transparent score that can be broken down component by component.
- **No invented numbers.** Every figure in an LLM-generated text is checked against the data passed to the
  model; any unmatched number discards the text in favour of a template.
- **Robustness.** Each recommended zone reports how often it stays in the plan across 200 simulations with
  perturbed weights.
- **Private by design.** Models run on the team's own GPU; no organisation data leaves the server.

## How it works

Territorial and organisational analysis are kept separate and only meet in the matching step.

### 1. Territorial Intelligence (`src/build.py`)

| Indicator | Source | Level |
|---|---|---|
| Population, share of foreign residents | AperTO, population and foreign residents by statistical zone | zone |
| Share aged 65+ and 80+, old-age index, 2013→2020 ageing trend | AperTO, population by single year of age and zone, 2013 and 2020 | zone |
| Widowed residents, people living alone | AperTO, marital status and household type by district, 2025 | district → zone |
| Economic assistance per 1,000 residents (total, employment, housing) | AperTO, economic assistance interventions by census section | zone |
| Mean distance from each address to the nearest ASL residential facility, local health facility and pharmacy | Regione Piemonte (ASL facilities, pharmacies) + AperTO street-number register (118,275 addresses) | address → zone |
| Zone boundaries | Geoportale, Comune di Torino | zone |

- District-level figures are allocated to zones by synthetic estimation (widowed residents in proportion to
  the population aged 65+, people living alone in proportion to total population).
- Assistance rates in small zones are shrunk towards the city mean.
- ASL facilities, published with addresses only, are geocoded on the street-number register by matching the
  set of words in the street name and the house number (219 of 251 located).
- Three composite indices — demographic isolation, service gap, fragility — are weighted by PCA (squared
  first-component loadings, OECD composite-indicator method). A k-means clustering groups the zones into five
  need profiles.

**Findings worth stating.** People living alone weigh roughly zero in the isolation index, because the
available figure covers all ages at district level and does not follow ageing. A supervised model (random
forest and ridge regression) trained to predict assistance rates from demographic factors had a negative
cross-validated R² and was discarded: the assistance data is distorted in central zones, most likely by
fictitious residence registrations of homeless people.

### 2. Organization Intelligence

An organisation profile holds name, category, mission, target groups, interventions it can deliver, annual
budget, staff and, optionally, the districts it works in. It can be filled in manually or extracted from free
text by the LLM, constrained by a JSON schema to the categories and interventions of `src/catalog.json`.
Neighbourhoods named in the text are mapped to their districts.

### 3. Matching & Recommendation

For every zone *n* and intervention *i* of organisation *o*:

```
Score = p_i · (0.35·NeedFit + 0.25·ServiceGap + 0.20·MissionFit + 0.20·Feasibility)
```

| Component | Meaning |
|---|---|
| NeedFit | Half the mean percentile of the needs the intervention addresses, half the percentile of the number of people concerned |
| ServiceGap | Percentile of the shortage of the service linked to the intervention |
| MissionFit | Cosine similarity between the mission and the intervention description (multilingual-e5 embeddings), rescaled to 0–1 |
| Feasibility | Scale fit between the organisation's capacity and the zone's need: min(capacity, need) / max(capacity, need) |

`p_i` is the priority the organisation assigns to that need. Each zone keeps its best intervention; zones with
fewer than 1,000 residents are excluded because their rates are unstable. Weights can be overridden per
request.

### 4. Social Impact Planner

For the top N zones the planner reports where (zone and score), why (indicators with percentile and city
median), how much (beneficiaries, staff and budget, with the budget split equally across zones and unit costs
from the catalogue) and which intervention. The LLM writes the narrative from these figures only.

## AI components

| Component | Model or method | Role |
|---|---|---|
| Profile extraction | Qwen3.8-27B (INT4), served with vLLM | Free text → schema-constrained JSON profile |
| Plan narrative | same model | Where / why / which intervention / how much, per zone |
| Plan Q&A | same model | Answers grounded in the plan and the zones mentioned |
| MissionFit | multilingual-e5-base embeddings | Semantic match between mission and interventions |
| Index weights and zone profiles | PCA, k-means (scikit-learn) | Data-driven weighting and segmentation |

If the LLM is unavailable, the map, ranking and plan keep working; texts fall back to templates and the chat to
rule-based answers.

## Getting started

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python src/build.py   # data/raw -> data/processed (zones.csv, zones.geojson, drivers.json)
bash serve/start_llm.sh         # LLM on :8001 and embeddings on :8002 (vLLM, GPU 1)
bash serve/start_api.sh         # API and web app on http://127.0.0.1:8700
```

Raw data in `data/raw/` is not versioned; the processed outputs in `data/processed/` are, so the API runs right
after cloning.

## API

| Method | Path | Returns |
|---|---|---|
| GET | `/data.js` | Zones with geometry and indicators for the web app |
| GET | `/api/zones` | GeoJSON of the 92 zones with indicators and percentiles |
| GET | `/api/zones/{zona}` | Zone card: indicators, percentiles, profile |
| GET | `/api/drivers` | PCA weights per index, k-means profiles, data coverage |
| GET | `/api/catalog` | Categories, target groups, interventions and unit costs |
| POST | `/api/org/parse` | Organisation profile extracted from `{"testo": "..."}` |
| POST | `/api/match` | Zone ranking with the four score components |
| POST | `/api/plan` | Plan, full ranking, robustness, MissionFit and narrative (`testo=false` skips the LLM) |
| POST | `/api/auto` | Profile extraction and plan in one call |
| POST | `/api/ask` | Grounded answer to a question about the plan, with sources |

Example profile:

```json
{
  "nome": "Example cooperative",
  "categoria": "cooperativa sociale",
  "missione": "contrastiamo la solitudine degli anziani con visite e attività di gruppo",
  "interventi": ["centro_incontro", "telesoccorso"],
  "priorita": {"centro_incontro": 1, "telesoccorso": 0.5},
  "budget": 80000,
  "operatori": 6,
  "circoscrizioni": [],
  "escluse": []
}
```

## Tech stack

| Layer | Technologies |
|---|---|
| Data analysis | Python 3.12, pandas, NumPy, GeoPandas, scikit-learn |
| Model serving | vLLM on an NVIDIA A40 |
| API | FastAPI, uvicorn, Pydantic, OpenAI-compatible client |
| Web app | HTML, CSS, vanilla JavaScript, MapLibre GL, D3 |

## Repository layout

```
data/raw/         downloaded open data (not versioned)
data/processed/   zone indicators used by the API
src/build.py      territorial indicators, PCA, k-means
src/api.py        profile, matching, planner, Q&A, API
src/catalog.json  interventions, unit costs, indicator labels
serve/            start scripts for models and API
web/              Welfare Compass web app and scripted demo (demo.js)
```

## Limitations

- Unit costs per beneficiary are default parameters chosen by the team, meant to be replaced by each
  organisation.
- Widowed residents and people living alone are estimated from district data.
- No open dataset of municipal social-care facilities (day centres, social service offices, private care
  homes) was found; service gaps are measured on ASL facilities and pharmacies.
- The number check blocks invented figures, not imprecise wording without numbers.

## Data sources

[AperTO — Comune di Torino open data](https://aperto.comune.torino.it) ·
[Regione Piemonte open data](https://www.dati.piemonte.it) ·
[Geoportale del Comune di Torino](http://geoportale.comune.torino.it)
