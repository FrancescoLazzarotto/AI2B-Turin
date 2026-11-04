# Social Impact Planner — Torino

Strumento che individua i quartieri di Torino a maggior rischio di isolamento
demografico o carenza di servizi (invecchiamento attivo, inclusione lavorativa,
fragilità urbane), per aiutare enti del terzo settore, fondazioni e istituzioni
a indirizzare i fondi dove generano più ritorno sociale.

## Fonti dati

- **AperTO** — portale open data del Comune di Torino (fonte principale)
- **Regione Piemonte** — open data regionali, strutture sociosanitarie (integrativa)

## Struttura

```
data/raw/         dati scaricati così come sono (non versionati)
data/processed/   dati puliti e aggregati per quartiere
notebooks/        esplorazione e analisi
src/              codice riutilizzabile (download, pulizia, indicatori)
```
