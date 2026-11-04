# Social Impact Planner — Torino

Indica a un'organizzazione del terzo settore in quali zone statistiche di Torino (92) può generare più impatto
sociale, con quale intervento, con quale budget e perché. Tutto è calcolato da open data pubblici e ogni
numero si può ricondurre alla sua fonte.

## Avvio

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python src/build.py   # data/raw -> data/processed (zones.csv, zones.geojson, drivers.json)
bash serve/start_llm.sh         # Qwen3.8-27B su :8001 + embedding e5 su :8002, GPU1
bash serve/start_api.sh         # API su http://127.0.0.1:8700
```

Senza LLM l'API funziona lo stesso: `/api/org/parse` non è disponibile, `/api/plan` usa un testo a modello.

## Come funziona

Le quattro fasi restano separate: gli indicatori territoriali non conoscono l'organizzazione, che entra
solo nel matching.

### 1. Territorial Intelligence — `src/build.py`

| Indicatore | Fonte | Livello |
|---|---|---|
| Popolazione, stranieri | AperTO, popolazione e stranieri per zona statistica | zona |
| Quota over 65 / over 80, indice di vecchiaia, variazione 2013→2020 | AperTO, età annuale per zona statistica 2013 e 2020 | zona |
| Vedovi, persone sole | AperTO, stato civile e famiglie per tipologia 2025 | circoscrizione → zona |
| Interventi di assistenza economica (totale, lavoro, casa) | AperTO, interventi per sezione di censimento | zona |
| Distanza media dei civici dalla struttura ASL residenziale, sanitaria territoriale, farmacia | Regione Piemonte (strutture ASL, farmacie) + stradario dei civici AperTO | civico → zona |
| Confini delle zone | Geoportale Comune di Torino | zona |

- **Stime per zona.** Vedovi e persone sole esistono solo per circoscrizione. Per le zone sono stimati
  così: i vedovi in proporzione agli over 65 della zona, le persone sole in proporzione alla popolazione.
- **Zone piccole.** I tassi di assistenza vengono avvicinati alla media cittadina nelle zone con pochi
  abitanti.
- **Tre indici:** isolamento demografico, carenza di servizi, fragilità socioeconomica. I pesi non sono
  scelti a mano: escono da un'analisi delle componenti principali (PCA) di ciascun gruppo di fattori (il
  metodo OECD per gli indici compositi) e sono in `/api/drivers`.
- **Profili di zona.** Un k-means sui tre indici raggruppa le zone in 5 profili.

Cosa è emerso dai dati, e va detto:
- La quota di persone sole ha peso circa 0 nell'indice di isolamento. Il dato disponibile riguarda tutte
  le età ed è per circoscrizione, quindi non segue l'invecchiamento: misura una cosa diversa, come i
  giovani soli del centro. Servirebbe il dato "anziani soli per zona".
- Un modello supervisionato addestrato a prevedere gli interventi di assistenza a partire dai fattori
  demografici non ha capacità predittiva (R² negativo in validazione incrociata), quindi è stato scartato.
  Il motivo: molti interventi risultano registrati in zone centrali (Municipio, Palazzo Reale), dove con
  ogni probabilità c'è la residenza fittizia di chi è senza dimora.
- Delle 251 strutture ASL di Torino ne sono state localizzate 219. Non è stato trovato nessun dataset aperto
  sulle strutture socio-assistenziali comunali, come i centri d'incontro o le RSA private.

### 2. Organization Intelligence

Il profilo (`Org`) contiene: nome, categoria, missione, destinatari, interventi, budget, operatori e,
facoltative, le circoscrizioni in cui lavorare. Si compila a mano oppure da testo libero con
`POST /api/org/parse`: un LLM locale estrae il profilo, vincolato a scegliere categorie, destinatari e
interventi dal catalogo in `src/catalog.json`.

### 3. Matching — `POST /api/match`

Per ogni zona *n* e per ogni intervento *i* dell'organizzazione:

```
Score = w1·NeedFit + w2·ServiceGap + w3·MissionFit + w4·Feasibility     (default 0.35 / 0.25 / 0.20 / 0.20)
```

- **NeedFit**: per metà il percentile degli indicatori di bisogno legati all'intervento, per metà il
  percentile del numero di persone interessate (intensità e volume insieme).
- **ServiceGap**: percentile della carenza del servizio legato all'intervento.
- **MissionFit**: somiglianza semantica (embedding e5) tra la missione dichiarata e la descrizione
  dell'intervento.
- **Feasibility**: adeguatezza di scala tra la capacità dell'organizzazione (beneficiari coperti con budget e
  operatori) e i beneficiari potenziali della zona, `min(capacità, bisogno) / max(capacità, bisogno)`. Vale 1
  quando le due dimensioni coincidono e scende sia se la zona è troppo grande sia se è troppo piccola.

Le zone con meno di 1000 residenti (9, quasi tutte in collina) non entrano nella classifica perché i loro tassi sono instabili.

Per ogni zona si tiene l'intervento con lo score più alto. I pesi si possono passare nella richiesta.

### 4. Social Impact Planner — `POST /api/plan`

Per le prime N zone (default 3):
- **dove**: la zona;
- **perché**: gli indicatori con il loro percentile e la mediana di Torino;
- **con quale intervento**: quello scelto dal matching;
- **quanto**: beneficiari, budget e operatori. Il budget è diviso in parti uguali tra le zone, i costi
  unitari sono parametri del catalogo.

Un LLM locale scrive il testo partendo solo da questi numeri. Se il testo contiene una cifra che non
compare nei dati viene scartato e si usa il testo a modello (`fonte_testo` indica quale dei due).

## API per il front-end

Il front-end (`index.html`, css, js) va in `web/`: l'API lo serve su `/`, quindi le chiamate usano
percorsi relativi (`/api/...`). Dopo aver caricato o cambiato i file: `bash serve/start_api.sh`.
Le chiamate da un'altra origine sono comunque abilitate (CORS).

| Metodo | Percorso | Risposta |
|---|---|---|
| GET | `/api/zones` | GeoJSON delle 92 zone, con tutti gli indicatori e i percentili `p_*` nelle proprietà (per la mappa) |
| GET | `/api/zones/{zona}` | Scheda della zona: indicatori, percentili, profilo |
| GET | `/api/drivers` | Pesi PCA dei fattori di ogni indice, profili k-means, copertura dei dati |
| GET | `/api/catalog` | Categorie, destinatari, interventi con i costi unitari |
| POST | `/api/org/parse` | `{"testo": "..."}` → profilo `Org` |
| POST | `/api/match?top=10` | `Org` → `mission_fit` per intervento + `ranking` delle zone con le 4 componenti |
| POST | `/api/plan?top=3` | `Org` → `piano` (dove/perché/quanto/intervento), `residui`, `testo`, `fonte_testo` |
| POST | `/api/auto?top=3` | `{"testo": "..."}` → `profilo` estratto + tutto quello che restituisce `/api/plan` |
| POST | `/api/ask` | `{"domanda": "...", "org": Org, "top": 3}` → `risposta` dell'LLM basata solo sui dati del piano e delle zone citate, `fonti` |
| GET | `/data.js` | `window.ZONE` (GeoJSON con indicatori) e `window.PROFILI_ZONA` per il front-end |

`/api/plan` restituisce anche `classifica` (tutte le zone candidate in ordine) e, per ogni zona del piano, la
`solidita`: la quota di 200 simulazioni, con i pesi perturbati, in cui la zona resta nel piano. Con `testo=false`
risponde in meno di un secondo, senza testo dell'LLM. `Org` accetta anche `escluse` (zone da non considerare) e
`priorita` (moltiplicatore dello score per intervento).

Il front-end in `web/` (Bussola Welfare) usa questi endpoint:
- "Compila con l'AI" chiama `/api/org/parse`;
- "Genera il piano" chiama `/api/plan`, prima senza testo e poi con il testo dell'LLM in background;
- "Chiedi al piano" chiama `/api/ask`, con risposte locali a regole fisse se l'LLM non risponde.

Esempio di `Org`:

```json
{
  "nome": "Cooperativa Esempio",
  "categoria": "cooperativa sociale",
  "missione": "contrastiamo la solitudine degli anziani con visite e attività di gruppo",
  "destinatari": ["anziani", "persone sole"],
  "interventi": [],
  "budget": 80000,
  "operatori": 6,
  "circoscrizioni": [],
  "pesi": {"need": 0.35, "gap": 0.25, "mission": 0.2, "feasibility": 0.2}
}
```

```js
const plan = await fetch("/api/plan?top=3", {
  method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(org)
}).then(r => r.json());
```

## Struttura

```
data/raw/         dati scaricati (non versionati)
data/processed/   output di build.py usati dall'API
src/build.py      Territorial Intelligence
src/api.py        Organization profile, matching, planner, API
src/catalog.json  interventi, costi unitari, etichette degli indicatori
serve/            avvio dei modelli e dell'API
```
