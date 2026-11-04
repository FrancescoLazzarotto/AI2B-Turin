import json
import math
import re
from functools import cache
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
Z = pd.read_csv(ROOT / "data/processed/zones.csv").set_index("zona")
GEO = json.loads((ROOT / "data/processed/zones.geojson").read_text())
DRIVERS = json.loads((ROOT / "data/processed/drivers.json").read_text())
CAT = json.loads((ROOT / "src/catalog.json").read_text())
INT = {c["id"]: c for c in CAT["interventi"]}
LABEL = CAT["etichette"]
MIN_POP = 1000
LLM = OpenAI(base_url="http://127.0.0.1:8001/v1", api_key="-", timeout=120)
EMB = OpenAI(base_url="http://127.0.0.1:8002/v1", api_key="-", timeout=30)

app = FastAPI(title="Social Impact Planner Torino")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class Pesi(BaseModel):
    need: float = 0.35
    gap: float = 0.25
    mission: float = 0.2
    feasibility: float = 0.2


class Org(BaseModel):
    nome: str = ""
    categoria: str = "altro"
    missione: str = ""
    destinatari: list[str] = []
    interventi: list[str] = []
    budget: float = Field(gt=0)
    operatori: int = Field(gt=0)
    circoscrizioni: list[int] = []
    pesi: Pesi = Pesi()


class Testo(BaseModel):
    testo: str


def embed(texts):
    r = EMB.embeddings.create(model="embed", input=[f"query: {t}" for t in texts])
    v = np.array([d.embedding for d in r.data])
    return v / np.linalg.norm(v, axis=1, keepdims=True)


@cache
def catalog_vectors():
    return embed([f"{c['nome']}. {c['descrizione']}" for c in CAT["interventi"]])


def mission_fit(missione):
    if not missione.strip():
        return {i: 1.0 for i in INT}
    s = catalog_vectors() @ embed([missione])[0]
    s = (s - s.min()) / (s.max() - s.min())
    return dict(zip(INT, s.round(3)))


def fmt(col, v):
    unit = LABEL.get(col, ["", ""])[1]
    if unit == "%":
        return f"{100 * v:.1f}%"
    if unit == "pt":
        return f"{100 * v:+.1f} punti"
    if unit == "m":
        return f"{v:.0f} m"
    if unit == "x100":
        return f"{100 * v:.0f}"
    if unit == "idx":
        return f"{v:.2f}"
    return f"{v:.1f}"


def ranking(org):
    w = org.pesi.model_dump()
    tot = sum(w.values())
    if tot <= 0:
        raise HTTPException(422, "almeno un peso deve essere maggiore di zero")
    w = {k: v / tot for k, v in w.items()}
    ids = [i for i in org.interventi if i in INT] or [c["id"] for c in CAT["interventi"] if set(c["destinatari"]) & set(org.destinatari)] or list(INT)
    mf = mission_fit(org.missione)
    zz = Z[Z["pop"] >= MIN_POP]
    zz = zz[zz.circ.isin(org.circoscrizioni)] if org.circoscrizioni else zz
    rows = []
    for i in ids:
        c = INT[i]
        need = 0.5 * zz[[f"p_{n}" for n in c["need"]]].mean(axis=1) + 0.5 * Z[c["target"]].rank(pct=True).reindex(zz.index)
        gap = zz[f"p_{c['gap']}"]
        benef = (zz[c["target"]] * c["copertura"]).clip(lower=1).round()
        cap = min(org.budget / c["costo"], org.operatori * c["per_operatore"])
        feas = np.minimum(cap, benef) / np.maximum(cap, benef)
        score = w["need"] * need + w["gap"] * gap + w["mission"] * mf[i] + w["feasibility"] * feas
        rows.append(pd.DataFrame({"zona": zz.index, "nome": zz.nome, "circ": zz.circ, "intervento": i, "score": score,
                                  "need_fit": need, "service_gap": gap, "mission_fit": mf[i], "feasibility": feas,
                                  "beneficiari_target": benef}))
    r = pd.concat(rows).sort_values("score", ascending=False).drop_duplicates("zona")
    return r.round(3).reset_index(drop=True), mf


def reasons(zona, c):
    z = Z.loc[zona]
    out = []
    for col in dict.fromkeys(c["need"] + [c["gap"]]):
        out.append({"indicatore": LABEL[col][0], "valore": fmt(col, z[col]), "mediana_torino": fmt(col, Z[col].median()),
                    "percentile": round(100 * z[f"p_{col}"])})
    return sorted(out, key=lambda d: -d["percentile"])


def allocate(org, r, top):
    budget, ops, plan = org.budget, org.operatori, []
    for row in r.head(top).itertuples():
        c = INT[row.intervento]
        n = int(min(row.beneficiari_target, org.budget / top // c["costo"], org.operatori / top * c["per_operatore"]))
        if n < 1:
            continue
        costo, operatori = n * c["costo"], math.ceil(n / c["per_operatore"])
        budget, ops = budget - costo, ops - operatori
        plan.append({"zona": int(row.zona), "nome": row.nome, "circoscrizione": int(row.circ), "score": row.score,
                     "intervento": c["nome"], "descrizione_intervento": c["descrizione"],
                     "perche": reasons(row.zona, c),
                     "beneficiari": n, "beneficiari_potenziali": int(row.beneficiari_target),
                     "costo_unitario_eur": c["costo"], "budget_eur": int(costo), "operatori": operatori,
                     "componenti": {"need_fit": row.need_fit, "service_gap": row.service_gap,
                                    "mission_fit": row.mission_fit, "feasibility": row.feasibility}})
    return plan, {"budget_residuo_eur": int(budget), "operatori_residui": ops}


def template(org, plan):
    out = []
    for p in plan:
        why = "; ".join(f"{d['indicatore']} {d['valore']} (mediana Torino {d['mediana_torino']})" for d in p["perche"][:3])
        out.append(f"**{p['nome']}** (zona {p['zona']}, circoscrizione {p['circoscrizione']})\n"
                   f"- Dove: {p['nome']}, punteggio {p['score']}.\n- Perché: {why}.\n"
                   f"- Con quale intervento: {p['intervento']}.\n"
                   f"- Quanto: {p['beneficiari']} beneficiari × {p['costo_unitario_eur']} € = {p['budget_eur']} €, {p['operatori']} operatori.")
    return "\n\n".join(out)


def numbers(s, rounded=False):
    out = set()
    for n in re.findall(r"\d+(?:[.,]\d+)*", s):
        out.add(re.sub(r"[.,]", "", n))
        if rounded and len(re.findall(r"[.,]", n)) == 1:
            out.add(str(round(float(n.replace(",", ".")))))
    return out


def narrative(org, plan):
    if not plan:
        return "Con il budget e gli operatori indicati non si raggiunge nemmeno un beneficiario nelle zone selezionate.", "template"
    facts = json.dumps({"organizzazione": org.nome, "missione": org.missione, "piano": plan}, ensure_ascii=False)
    prompt = ("Sei un consulente per enti del terzo settore. Scrivi in italiano il piano d'intervento per l'organizzazione, "
              "una sezione per zona con titolo in grassetto e quattro voci: Dove, Perché, Con quale intervento, Quanto. "
              "Usa SOLO i numeri presenti nei dati, copiati identici; non aggiungere stime, percentuali o cifre nuove. "
              "Sii concreto e breve, massimo 90 parole per zona.\n\nDATI:\n" + facts)
    try:
        r = LLM.chat.completions.create(model="llm", messages=[{"role": "user", "content": prompt}], temperature=0.2, max_tokens=900)
        text = r.choices[0].message.content.strip()
    except Exception:
        return template(org, plan), "template"
    extra = {n for n in numbers(text) - numbers(facts, rounded=True) if int(n) > 10}
    return (text, "llm") if not extra else (template(org, plan), "template")


def mentioned_circ(text):
    text = text.lower()
    found = set()
    for zona, nome in Z.nome.items():
        for part in nome.lower().replace("(", " - ").replace(")", "").split(" - "):
            part = part.strip()
            words = part.split()
            if not words:
                continue
            keys = [part] + ([" ".join(words[1:])] if words[0] in ("nuova", "borgata", "borgo") and len(words) > 1 else [])
            if any(len(k) >= 5 and k in text for k in keys):
                found.add(int(Z.circ[zona]))
    return found


@app.get("/api/zones")
def zones():
    return GEO


@app.get("/api/zones/{zona}")
def zone(zona: int):
    if zona not in Z.index:
        raise HTTPException(404)
    z = Z.loc[zona]
    ind = {k: {"etichetta": v[0], "valore": fmt(k, z[k]), "percentile": round(100 * z[f"p_{k}"])} for k, v in LABEL.items() if f"p_{k}" in z}
    return {"zona": zona, "nome": z.nome, "circoscrizione": int(z.circ), "popolazione": int(z["pop"]),
            "over65": int(z.over65), "over80": int(z.over80), "profilo": DRIVERS["profili"][int(z.profilo)]["etichetta"],
            "indicatori": ind}


@app.get("/api/drivers")
def drivers():
    return DRIVERS


@app.get("/api/catalog")
def catalog():
    return CAT


@app.post("/api/org/parse")
def parse(t: Testo):
    schema = Org.model_json_schema()
    schema["properties"]["categoria"] = {"enum": CAT["categorie"]}
    schema["properties"]["destinatari"] = {"type": "array", "items": {"enum": CAT["destinatari"]}, "maxItems": 3}
    schema["properties"]["interventi"] = {"type": "array", "items": {"enum": list(INT)}, "maxItems": 3}
    schema["properties"]["circoscrizioni"] = {"type": "array", "items": {"type": "integer", "minimum": 1, "maximum": 8}, "maxItems": 8}
    schema["properties"].pop("pesi")
    schema.pop("$defs", None)
    schema["required"] = ["nome", "categoria", "missione", "destinatari", "interventi", "budget", "operatori", "circoscrizioni"]
    cat = "\n".join(f"- {c['id']}: {c['descrizione']}" for c in CAT["interventi"])
    prompt = ("Estrai il profilo dell'organizzazione dal testo. Interventi possibili:\n" + cat +
              "\nUna fondazione bancaria è 'fondazione'. Destinatari: scegli solo quelli citati o implicati dal testo. "
              "Circoscrizioni di Torino 1-8: indica solo quelle citate esplicitamente, altrimenti lista vuota. "
              "Budget in euro annui. Se un dato manca usa budget 10000 e operatori 1.\n\nTESTO:\n" + t.testo)
    try:
        r = LLM.chat.completions.create(model="llm", messages=[{"role": "user", "content": prompt}], temperature=0, max_tokens=600,
                                        response_format={"type": "json_schema", "json_schema": {"name": "org", "schema": schema}})
    except Exception:
        raise HTTPException(503, "LLM non disponibile")
    try:
        org = Org.model_validate_json(r.choices[0].message.content)
    except ValueError:
        raise HTTPException(502, "profilo non estratto: riformula il testo o compila il modulo")
    org.destinatari = list(dict.fromkeys(org.destinatari))
    org.interventi = list(dict.fromkeys(org.interventi))
    org.circoscrizioni = sorted(set(org.circoscrizioni) | mentioned_circ(t.testo))
    return org


@app.post("/api/match")
def match(org: Org, top: int = 92):
    r, mf = ranking(org)
    return {"mission_fit": mf, "ranking": r.head(top).to_dict("records")}


@app.post("/api/plan")
def plan(org: Org, top: int = 3):
    r, mf = ranking(org)
    p, resto = allocate(org, r, top)
    text, source = narrative(org, p)
    return {"piano": p, "residui": resto, "testo": text, "fonte_testo": source}


@app.post("/api/auto")
def auto(t: Testo, top: int = 3):
    org = parse(t)
    return {"profilo": org, **plan(org, top)}


if (ROOT / "web").is_dir():
    app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
