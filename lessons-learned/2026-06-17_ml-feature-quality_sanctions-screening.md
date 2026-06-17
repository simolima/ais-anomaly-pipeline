# Qualità delle feature ML, screening sanzioni e operatività dbt locale

**Data:** 2026-06-17
**Contesto:** primo run end-to-end di `ais_ml` dopo il completamento del backfill 2024.
**Workspace:** `7474660162002917` (Databricks Free Edition Serverless)
**File toccati:** `dbt/models/gold/vessel_features.sql`, `ml/isolation_forest.py`,
`orchestration/commit_window.py`, `databricks.yml`, `~/.dbt/profiles.yml` (config locale)

---

## 1. `raise SystemExit(0)` sembra un fallimento su Serverless

**Sintomo:** i run di `ais_dbt` a backfill concluso mostravano `SystemExit: 0` + "Workload
failed, see run output for details", con tanto di `To exit: use 'exit', 'quit', or Ctrl-D`.

**Causa:** nel contesto IPython di Databricks Serverless un `SystemExit` *sollevato* viene
intercettato dalla REPL e presentato come fallimento, **anche con exit code 0** (che è un
successo). Il run no-op (watermark oltre 2024-12-31 → sentinel 2999) era corretto.

**Fix:** in `commit_window.py` sostituito `raise SystemExit(0)` con normale `if/else`. Il
no-op ora finisce verde. Stessa accortezza vale per gli altri script (`isolation_forest.py`,
`send_alert.py`) che usano il pattern come guardia "niente da fare".

**Lezione:** su Serverless non usare `raise SystemExit` per uscite pulite a metà script —
usa il controllo di flusso.

---

## 2. Backfill finito → job manual-only, non schedule in pausa

Completato il 2024, le schedule di `ais_ingest`/`ais_dbt` sono state **rimosse** (job
manual-only), non lasciate `PAUSED`. Una schedule attiva farebbe solo girare a vuoto il
sentinel 2999 bruciando compute. Attenzione ai conflitti git: nel frattempo era stata
mergiata una PR che metteva `ais_dbt` su schedule **oraria UNPAUSED** (serviva per accelerare
il backfill) → conflitto risolto tenendo la versione manual-only.

---

## 3. La separazione dev/prod ESISTE — ma solo per i modelli dbt (via macro)

**Scoperta chiave.** Il workspace ha un solo Unity Catalog (`workspace`), quindi sembra non
ci sia isolamento dev/prod. **Ma per i modelli dbt c'è**, a livello di schema, grazie a
`dbt/macros/generate_schema_name.sql`:

| Target dbt | schema `gold` diventa | schema `silver` diventa |
|---|---|---|
| `dev` (default del profilo locale) | `bronze_gold` (sandbox) | `bronze_silver` |
| qualsiasi altro (`prod`, il job) | `gold` (reale) | `silver` |

**Sintomo:** `dbt run --select vessel_features` in locale falliva con
`TABLE_OR_VIEW_NOT_FOUND: workspace.bronze_gold.ais_dark_gaps`.

**Causa:** il profilo locale ha `target: dev` → scrive nel sandbox `bronze_gold`, **mai
popolato** (tutto il backfill è passato dal job = target ≠ dev = `gold`).

**Fix:** aggiunto un target `prod` a `~/.dbt/profiles.yml` (copia di `dev`, stessa
connessione/token) e lanciato `dbt run --select vessel_features --target prod`.

**Lezione:** per scrivere sui dati reali da locale serve un target **≠ `dev`**. Il sandbox
`dev` è la palestra (non rovina la prod), ma è vuoto finché non ci giri esplicitamente.
La separazione vale solo per silver/gold; bronze e il catalogo sono condivisi.

---

## 4. `dbt run` locale scrive DIRETTAMENTE sui dati di prod

Conseguenza del catalogo unico: un `dbt run --target prod` da locale scrive sugli stessi
`gold.*` che usa il job, **a prescindere dal branch git**. Il branch/PR conta solo per la
storia del *codice*, non per *quali dati* vengono scritti (contano solo i file nel working
tree + il target). Tenerlo presente: niente `--full-refresh` con vars in locale.

---

## 5. `vessel_features` è un `table` aggregato → ricostruibile senza backfill

`gold.vessel_features` è `materialized='table'` (non windowed). Si ricostruisce **in una
singola run** dai detail già persistiti (`dbt run --select vessel_features`), senza rifare le
~52 finestre. È la leva per correggere le feature ML senza toccare i modelli incrementali.

---

## 6. Gli artefatti di `ais_impossible_speed`: la distanza è il vero discriminante

`implied_speed = distance_nm / elapsed_hours` con solo `dt > 0` produce velocità assurde:

- **jitter GPS** (ping a ~secondi, wiggle sub-nm) → milioni di nodi senza movimento reale;
- **posizioni garbage** (0,0 / sentinella) → "salto" di migliaia di nm in un passo;
- **traghetti veloci** (SeaStreak, Catalina, Key West Express: crociera 35-45 kn) → trippano
  la regola dei 30 kn a ogni ping e, pingando di continuo, accumulano **decine di migliaia**
  di eventi, sommergendo le anomalie vere nel *conteggio*.

**Errore intermedio:** cappare `implied_speed <= 90`. Sbagliato: rimuove **anche i teleport
reali** (un salto grande su un gap normale ha velocità implicita altissima).

**Fix corretto:** filtrare per **distanza** (il discriminante pulito), non per velocità:
`distance_nm between 2 and 500 AND implied_speed_knots > 50`. Esclude jitter (<2nm),
posizioni-garbage (>500nm) e crociera traghetti (<50kn), tenendo i veri salti impossibili.

---

## 7. Screening sanzioni su MMSI da solo = falsi positivi

**Il finding più importante.** Cross-reference AIS ↔ OpenSanctions sul **solo MMSI** dà
falsi positivi, perché l'MMSI viene **riassegnato/riusato** (cambio bandiera o transponder).
Verificato online: l'**IMO** è l'identità permanente dello scafo (mai riassegnata), l'**MMSI**
no, e l'AIS trasmette l'MMSI. → un match di solo-MMSI non identifica univocamente la nave.

In questo dataset **tutti e 5** i match erano collisioni (nome **e** bandiera discordanti):

| MMSI | OpenSanctions | AIS reale (da registri) |
|---|---|---|
| 249256000 | SINA (OFAC SDN, flag Panama) | **LUIGI GALVANI**, gas tanker LPG, Malta, IMO 9738246 |
| 256843000 | ARGO I (flag Panama) | GREENVILLE |
| 256845000 | APAMA (flag Iran) | GREENFIELD |
| 256865000 | DIAMOND II (flag Panama) | KALLONE |

**Fix (POC):** estrarre il meglio dall'MMSI → corroborare con **MMSI + nome** normalizzato
(`is_sanctioned`), e tenere `sanctions_mmsi_only_hit` per le collisioni "da investigare".
Risultato atteso su questi dati: **zero hit confermati** (realistico — le navi OFAC
shadow-fleet non trasmettono AIS in acque costiere USA).

### Limite documentato

Lo screening robusto richiederebbe il match per **IMO** (identità di scafo), ma il pull
OpenSanctions attuale ha `imo_number` **tutto null**, mentre i dati AIS *hanno* il campo
`imo`. Fix definitivo (fuori scope POC): rifare `02_ingest_sanctions_bronze.py` popolando
l'IMO, poi joinare `ais.imo = sanctions.imo_number`. Tocca solo l'ingestion sanzioni, non il
backfill AIS.

---

## 8. I quattro identificatori (per non confonderli)

| Campo | Cos'è | Permanente | Utile per il join? |
|---|---|---|---|
| `entity_id` | ID interno OpenSanctions del *record* | sì (nel loro DB) | No (non è un id di nave) |
| `entity_name` | nome dell'entità (per navi = nome nave) | No (si rinominano) | Debole (corroborazione) |
| `mmsi` | identità radio/registrazione, trasmessa via AIS | No (riassegnabile) | Chiave attuale, ma debole |
| `imo_number` | identità dello scafo, 7 cifre | **Sì** | **La migliore** (qui null) |

OpenSanctions: 511 entità, solo **63 con MMSI** — molte non sono navi (persone/società) e
comunque l'MMSI è volatile/ignoto. L'MMSI è la chiave **meno popolata e meno affidabile**.

---

## 9. La feature `is_sanctioned` veniva "sepolta" dal modello

Anche con un hit (fosse stato vero), l'Isolation Forest tratta `is_sanctioned` come **una
delle 8 feature pesate uguali**: navi con comportamento mite ma sanzionate finivano in fondo
(rank ~2195/77345). Per la sicurezza marittima "è su lista sanzioni" è **lo** segnale, non
uno qualsiasi → andrebbe gestito come **tier prioritario** (watchlist sempre in cima),
separato dal ranking comportamentale. Design a due tier:
`Tier 1 = sanzioni confermate` (qui vuoto), `Tier 2 = anomalie comportamentali`.

---

## 10. Query ad-hoc a Databricks da locale

Per ispezionare i dati senza job: `databricks-sql-connector` (già dipendenza di
dbt-databricks) via Python, leggendo host/http_path/token dal target `prod` di
`~/.dbt/profiles.yml` (senza stamparli). Utile per diagnostica veloce (overlap sanzioni,
forma tabelle) senza passare da un run dbt o da un notebook.

---

## 11. Verificare le affermazioni prima di documentarle

Avevo scritto in un commento che LUIGI GALVANI era "una nave da ricerca italiana": **falso**,
è un gas tanker LPG maltese (confusione con la OGS EXPLORA). Una ricerca sui registri navali
l'ha corretto **prima** che l'errore finisse nella doc. Lezione: per affermazioni fattuali
(identità navi, status sanzioni) verificare sulle fonti, non andare a memoria.
