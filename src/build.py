import json

import geopandas as gpd
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.neighbors import BallTree
from sklearn.preprocessing import StandardScaler

RAW = "data/raw"
OUT = "data/processed"
CRS = "EPSG:3003"

INDICI = {
    "isolamento": ["quota_over65", "quota_over80", "indice_vecchiaia", "vedovi_1000", "soli_1000"],
    "carenza_servizi": ["dist_residenziale", "dist_sanita", "dist_farmacia", "carenza_strutture"],
    "fragilita": ["quota_stranieri", "ass_tot_1000", "ass_lavoro_1000", "ass_casa_1000"],
}


def zone_code(s):
    return s.astype(str).str.extract(r"(\d+)")[0].astype(int)


def points(df, x, y):
    return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df[x], df[y]), crs="EPSG:4326").to_crs(CRS)


def tokens(via):
    return frozenset(via.upper().replace(".", " ").split())


def geocode(df, civ):
    streets = {tokens(v): v for v in civ.VIA.unique()}

    def match(via):
        t = tokens(via)
        if t in streets:
            return streets[t]
        sub = [s for s in streets if len(s) > 1 and s <= t]
        return streets[max(sub, key=len)] if sub else None

    via = df.indirizzo.map(match)
    num = df.numero_civico.astype(str).str.extract(r"(\d+)")[0]
    exact = civ.groupby([civ.VIA, civ.CIVICO.str.extract(r"(\d+)")[0]])[["x", "y"]].mean().apply(tuple, axis=1).to_dict()
    street = civ.groupby("VIA")[["x", "y"]].mean().apply(tuple, axis=1).to_dict()
    xy = pd.DataFrame([exact.get((v, n)) or street.get(v, (np.nan, np.nan)) for v, n in zip(via, num)],
                      index=df.index, columns=["x", "y"])
    ok = xy.x.notna()
    return gpd.GeoDataFrame(df[ok], geometry=gpd.points_from_xy(xy.x[ok], xy.y[ok]), crs="EPSG:4326").to_crs(CRS)


def rate(count, base, k=2000):
    count = count.reindex(base.index).fillna(0)
    return 1000 * (count + k * count.sum() / base.sum()) / (base + k)


def nearest(src, dst):
    return BallTree(np.c_[dst.geometry.x, dst.geometry.y]).query(np.c_[src.geometry.x, src.geometry.y])[0][:, 0]


zones = gpd.read_file(f"{RAW}/zone_statistiche_geo/zone_statistiche_geo.shp").set_crs(CRS, allow_override=True)
zones["zona"] = zone_code(zones.ZONASTAT)
zones = zones.dissolve("zona")[["geometry"]]

pop = pd.read_csv(f"{RAW}/y_5798.csv", sep=";").rename(columns={"Num_zona_stat": "zona", "Desc_zona_stat": "nome"})
pop = pop.assign(zona=zone_code(pop.zona), n=pop.femmine + pop.maschi).query("zona > 0").groupby("zona")
z = pd.DataFrame({"nome": pop.nome.first().str.title(), "pop": pop.n.sum()})
stra = pd.read_csv(f"{RAW}/zone_statistiche.csv", sep=";")
z["stranieri"] = (stra.femmine + stra.maschi).groupby(zone_code(stra.num_zona_stat)).sum()

def ages(year):
    e = pd.read_csv(f"{RAW}/eta_zona_{year}.csv", skiprows=1, index_col=0).fillna(0)
    e.index = e.index.astype(int)
    return e.T.groupby(zone_code(pd.Series(e.columns)).values).sum()


eta = ages(2020)
tot = eta.sum(axis=1)
eta13 = ages(2013)
z["quota_over65"] = eta.loc[:, 65:].sum(axis=1) / tot
z["quota_over80"] = eta.loc[:, 80:].sum(axis=1) / tot
z["indice_vecchiaia"] = eta.loc[:, 65:].sum(axis=1) / eta.loc[:, :14].sum(axis=1)
z["trend_over65"] = z.quota_over65 - eta13.loc[:, 65:].sum(axis=1) / eta13.sum(axis=1)
z["trend_over80"] = z.quota_over80 - eta13.loc[:, 80:].sum(axis=1) / eta13.sum(axis=1)
z["over65"] = (z.quota_over65 * z["pop"]).round()
z["over80"] = (z.quota_over80 * z["pop"]).round()
z["quota_stranieri"] = z.stranieri / z["pop"]
z = z.join(zones, how="inner")
z["densita"] = z["pop"] / (gpd.GeoSeries(z.geometry, crs=CRS).area / 1e6)

civ = pd.read_csv(f"{RAW}/iae19.csv", sep=";", dtype=str)
civ["x"] = civ.COORDINATA_X.str.replace(",", ".").astype(float)
civ["y"] = civ.COORDINATA_Y.str.replace(",", ".").astype(float)
civ["circ"] = civ.CIRCOSCRIZIONE.astype(int)
zone_gdf = gpd.GeoDataFrame(z[["geometry"]], crs=CRS)
civ_g = gpd.sjoin(points(civ, "x", "y"), zone_gdf, predicate="within")
z["circ"] = civ_g.groupby("zona").circ.agg(lambda s: s.mode().iat[0])

circ_pop = z.groupby("circ")["pop"].sum()
circ_over65 = z.groupby("circ").over65.sum()
sc = pd.read_csv(f"{RAW}/stato_civile_circ_2025.csv", sep=";").set_index("stato_civile")
fam = pd.read_csv(f"{RAW}/famiglie_tipologia_circ_2025.csv", sep=";", encoding="latin1").set_index("tipologia_famiglia")
cols = [f"circ_{i}" for i in range(1, 9)]
vedovi = sc.loc[sc.index.str.contains("edov"), cols].sum()
soli = fam.loc[["Femmine sole", "Maschi soli"], cols].sum()
vedovi.index = soli.index = range(1, 9)
z["vedovi_stima"] = (z.over65 * z.circ.map(vedovi / circ_over65)).round()
z["soli_stima"] = (z["pop"] * z.circ.map(soli / circ_pop)).round()
z["vedovi_1000"] = 1000 * z.vedovi_stima / z["pop"]
z["soli_1000"] = 1000 * z.soli_stima / z["pop"]

ass = pd.read_csv(f"{RAW}/sezioni_censimento.csv")
ass.columns = ["id", "tipo", "mesi", "importo", "sezione", "zona"]
g = ass.assign(
    lavoro=ass.tipo.str.contains("LAVORO|TIROCINI|INSERIMENTO"),
    casa=ass.tipo.str.contains("LOCAZIONE|ALBERGHI|RISCALDAMENTO|CONDOMINIALI|MANUTENZIONE|ABITAZIONE"),
    anziani=ass.tipo.str.contains("ANZIANO"),
).groupby("zona")
z["assistiti"] = g.size().reindex(z.index).fillna(0)
z["ass_tot_1000"] = rate(g.size(), z["pop"])
z["ass_lavoro_1000"] = rate(g.lavoro.sum(), z["pop"])
z["ass_casa_1000"] = rate(g.casa.sum(), z["pop"])
z["ass_anziani_1000over65"] = rate(g.anziani.sum(), z.over65)

asl = pd.read_csv(f"{RAW}/y_22171.csv", sep=";", dtype=str)
asl = asl[asl.desc_comune == "TORINO"].drop_duplicates(["denom_struttura", "indirizzo", "numero_civico"])
n_asl = len(asl)
asl = geocode(asl, civ)
res = asl[asl.desc_tipo_struttura.isin(["RESIDENZIALE", "SEMIRESIDENZIALE"])]
san = asl[~asl.index.isin(res.index)]
far = pd.read_csv(f"{RAW}/y_22166.csv", encoding="latin1", dtype=str)
far = far[(far.DESCRIZIONECOMUNE == "TORINO") & (far.DATAFINEVALIDITA == "-")].drop_duplicates("CODICEIDENTIFICATIVOFARMACIA")
far["lat"] = far.LATITUDINE.str.replace(",", ".").astype(float)
far["lon"] = far.LONGITUDINE.str.replace(",", ".").astype(float)
far = points(far, "lon", "lat")

civ_p = civ_g[["zona", "geometry"]].copy()
for name, dst in [("residenziale", res), ("sanita", san), ("farmacia", far)]:
    civ_p[name] = nearest(civ_p, dst)
    z[f"dist_{name}"] = civ_p.groupby("zona")[name].mean().round()
z["strutture"] = gpd.sjoin(asl, zone_gdf, predicate="within").groupby("zona").size().reindex(z.index).fillna(0)
z["strutture_10000"] = 10000 * z.strutture / z["pop"]
z["carenza_strutture"] = -z.strutture_10000

pesi = {}
for idx, fs in INDICI.items():
    x = StandardScaler().fit_transform(z[fs])
    pca = PCA(1).fit(x)
    load = pca.components_[0] * np.sign(pca.components_[0].sum())
    pesi[idx] = {"varianza_spiegata": round(float(pca.explained_variance_ratio_[0]), 3),
                 "fattori": {f: {"peso": round(float(l ** 2), 3), "direzione": int(np.sign(l))} for f, l in zip(fs, load)}}
    for f in fs:
        z[f"p_{f}"] = z[f].rank(pct=True)
    z[idx] = sum(z[f"p_{f}"] * l ** 2 * np.sign(l) for f, l in zip(fs, load))
    z[f"p_{idx}"] = z[idx].rank(pct=True)
for c in ["trend_over65", "trend_over80", "ass_anziani_1000over65", "over65", "over80", "stranieri", "assistiti", "pop"]:
    z[f"p_{c}"] = z[c].rank(pct=True)

km = KMeans(5, n_init=20, random_state=0).fit(z[[f"p_{i}" for i in INDICI]])
z["profilo"] = km.labels_
profili = []
for k, c in enumerate(km.cluster_centers_):
    alto = [i for i, v in zip(INDICI, c) if v >= 0.6]
    basso = [i for i, v in zip(INDICI, c) if v <= 0.4]
    profili.append({"id": k, "zone": int((km.labels_ == k).sum()), "centro": dict(zip(INDICI, np.round(c, 2).tolist())),
                    "etichetta": (" + ".join(f"{i} alto" for i in alto) or "nella media") + ("; " + ", ".join(f"{i} basso" for i in basso) if basso else "")})

geo = gpd.GeoDataFrame(z.reset_index(), crs=CRS).to_crs("EPSG:4326")
geo.to_file(f"{OUT}/zones.geojson", driver="GeoJSON")
geo.drop(columns="geometry").to_csv(f"{OUT}/zones.csv", index=False)
json.dump({"indici": pesi, "profili": profili,
           "copertura": {"zone": len(z), "strutture_asl_localizzate": len(asl), "strutture_asl_torino": n_asl, "farmacie": len(far)}},
          open(f"{OUT}/drivers.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(json.load(open(f"{OUT}/drivers.json")), ensure_ascii=False))
