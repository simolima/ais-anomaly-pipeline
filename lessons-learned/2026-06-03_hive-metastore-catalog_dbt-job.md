# dbt job fallisce con "UC_HIVE_METASTORE_DISABLED_EXCEPTION"

**Data:** 2026-06-03
**Comando coinvolto:** `databricks bundle run ais_dbt --target prod` (task `dbt_transform`)
**Workspace:** `https://dbc-f2967afc-a9f1.cloud.databricks.com` (Databricks Free Edition Serverless)
**Warehouse:** `dfaee2d99ca6e1e1`

---

## Sintomo

Il primo `dbt run` reale del job (modello `silver.ais_clean`) falliva subito, saltando tutto il resto:

```
1 of 5 START sql incremental model workspace.silver.ais_clean ... [RUN]
1 of 5 ERROR creating sql incremental model workspace.silver.ais_clean ... [ERROR]
2..5 SKIP

Database Error in model ais_clean
  [UC_HIVE_METASTORE_DISABLED_EXCEPTION] The operation attempted to use Hive
  Metastore, which is disabled ... Please double check the default catalog in
  current session and default namespace setting. SQLSTATE: 0A000
```

Nota chiave nel log: il target del modello era già `workspace.silver.ais_clean` (catalog
giusto), eppure l'operazione cadeva su hive_metastore. Lungo la strada è emerso anche un
**secondo bug** indipendente (vedi sotto), nascosto finché il primo non era risolto.

---

## Causa reale

Sul job, dbt **non** usa il profilo locale `~/.dbt/profiles.yml`: il **dbt_task di Databricks
genera al volo il suo `profiles.yml`** (target `databricks_cluster`). Quel profilo generato
**non impostava alcun `catalog`** → il **catalog di default della sessione** cadeva su
`hive_metastore`, che in Free Edition è **disabilitato**.

Punto cruciale e contro-intuitivo:

- Pinnare le **relazioni** a `workspace` (via `+database` sui modelli e `database` sui source)
  è **necessario ma NON sufficiente**.
- dbt-databricks esegue anche **operazioni non qualificate** (creazione schema, lookup di
  metadata) che usano il **default di sessione**. Con default = hive_metastore, queste
  falliscono — **anche se** la `create or replace table` è perfettamente qualificata come
  `workspace.silver.ais_clean`.

### Bug secondario trovato durante la diagnosi (Jinja whitespace)

I modelli a finestra avevano `{%- set apply_window = ... -%}` subito prima del `with` di
testa. Il `-%}` (trim del whitespace a destra) **mangiava il newline** tra l'ultimo commento
`-- ...` e `with ... as (`, incollando l'apertura della CTE **dentro** il commento →
`)` non bilanciata → `PARSE_SYNTAX_ERROR`. Si vedeva solo a runtime (parse/compile non lo
prendono). Fix: togliere il trim → `{% set apply_window = ... %}`.

---

## I fix applicati (3, complementari)

| # | File | Fix | A cosa serve |
|---|---|---|---|
| 1 | `dbt/dbt_project.yml` | `+database: workspace` sui modelli | nomi relazione modelli → `workspace.*` |
| 2 | `dbt/models/sources.yml` | `database: workspace` sul source bronze | letture source → `workspace.bronze.*` |
| 3 | `databricks.yml` (dbt_task) | `catalog: workspace` + `schema: bronze` | **default di sessione** del profilo generato → workspace |
| + | 4 modelli windowed | `{%- ... -%}` → `{% ... %}` su `set apply_window` | bug Jinja: `with` non più dentro un commento |

Il fix **#3 è quello risolutivo**; #1/#2 da soli non bastavano (dimostrato sotto).

---

## Come l'ho diagnosticato (comandi usati, in ordine)

### 1. Confermare che il profilo LOCALE è sano
```bash
cd dbt && dbt debug
```
**Esito:** `catalog: workspace`, `Connection test: OK`, `All checks passed!`. Quindi il
problema non era il profilo locale → era qualcosa di specifico del job.

### 2. Confrontare gli ambienti (job vs locale)
Dal log del job: `dbt=1.11.8`, `databricks=1.12.0`, **`target='databricks_cluster'`**, 8 thread.
In locale: `dbt=1.10.19`, target `dev`, 4 thread, catalog workspace. → Due ambienti diversi:
il `target='databricks_cluster'` è il **profilo generato da Databricks**, che non avevamo mai
ispezionato.

### 3. Pinnare il catalog sulle relazioni e verificare con compile (statico, niente warehouse)
```bash
dbt parse
dbt compile --select ais_clean --vars '{"start_date":"2024-01-01","end_date":"2024-01-07"}'
# verifica che il source risolva su workspace:
grep "from .workspace..bronze." target/compiled/.../silver/ais_clean.sql
# -> select * from `workspace`.`bronze`.`ais_raw`   ✅
```

### 4. (Bug Jinja) verificare che `with` non finisca dentro un commento
```bash
for m in ais_clean ais_dark_gaps ais_impossible_speed ais_anomaly_cues; do
  grep -nE "^\s*--.*\bwith\b.*\bas\b\s*\(" target/compiled/.../$m.sql && echo "BUG $m" || echo "OK $m"
done
# -> tutti OK dopo il fix
```

### 5. TEST SICURO in ambiente dev: eseguire davvero il modello, ma a costo ~zero
> **Perché è sicuro** — vedi sezione "Come e dove ho testato" sotto. In sintesi: target `dev`
> (scrive in uno schema **isolato** `workspace.bronze_silver.*`, NON in prod) e finestra
> **2023** (in bronze c'è solo il 2024 → **0 righe** processate, nessuno scan pesante).
```bash
dbt run --select ais_clean --vars '{"start_date":"2023-01-01","end_date":"2023-01-01"}'
# -> OK created sql incremental model bronze_silver.ais_clean [OK in 10.84s]
```
**Esito:** la SQL gira contro Databricks senza errori → **il codice è corretto**. Ma il profilo
locale ha `catalog: workspace`, quindi questo NON riproduceva ancora la condizione del job.

### 6. Riprodurre la condizione ESATTA del job, in isolamento (profilo temporaneo senza catalog)
> **Perché è sicuro** — uso un `--profiles-dir` in `/tmp`, **senza toccare** il vero
> `~/.dbt/profiles.yml`. Costruito da uno script che copia il target `dev` e ne **rimuove**
> solo il `catalog`.
```bash
mkdir -p /tmp/dbttest
python3 - <<'PY'
import yaml
p = yaml.safe_load(open('/Users/simon/.dbt/profiles.yml'))
dev = dict(p['ais_databricks']['outputs']['dev']); dev.pop('catalog', None)
yaml.safe_dump({'ais_databricks':{'target':'nocat','outputs':{'nocat':dev}}},
               open('/tmp/dbttest/profiles.yml','w'))
PY
dbt run --select ais_clean --profiles-dir /tmp/dbttest \
  --vars '{"start_date":"2023-01-01","end_date":"2023-01-01"}' --debug
```
**Esito:** **riprodotto** lo stesso `UC_HIVE_METASTORE_DISABLED_EXCEPTION`. Prova definitiva che
la causa è il **catalog assente nel profilo** (= default di sessione hive_metastore).

### 7. Catturare l'istruzione esatta che fallisce
```bash
... --debug 2>&1 | grep -iE "create or replace|create schema|use catalog"
# -> create or replace table `workspace`.`silver`.`ais_clean`   (QUALIFICATA, eppure fallisce)
```
Conferma: la `CREATE` è qualificata → a fallire è un'operazione **non qualificata** che usa il
default di sessione → serve impostare il catalog nel profilo.

### 8. Fix nel dbt_task + validazione
```yaml
# databricks.yml -> job ais_dbt -> task dbt_transform -> dbt_task:
catalog: workspace
schema: bronze
```
```bash
databricks bundle validate --target prod
# -> Validation OK!   (i campi catalog/schema sono accettati dal dbt_task)
```

---

## Come e dove ho testato (e perché è sicuro)

Tre livelli, dal più innocuo al più realistico, **senza mai toccare i dati di prod**:

1. **`dbt parse` / `dbt compile`** — puramente **statici**, non si connettono ad alcun
   warehouse, non scrivono nulla. Servono a verificare che la SQL renderizzata sia quella
   attesa (catalog corretto, `with` su riga propria).

2. **`dbt run` in target `dev`** — il macro `generate_schema_name` antepone il prefisso del
   target solo per `dev`: i modelli finiscono in `workspace.bronze_silver.*` /
   `workspace.bronze_gold.*`, **schemi isolati**, NON in `workspace.silver.*` di produzione.
   In più la finestra **2023** (dato assente: bronze è solo 2024) fa processare **0 righe** →
   compute trascurabile e zero rischio di full-scan dei 2B record. È una vera esecuzione
   contro Databricks, ma sandboxata.

3. **`--profiles-dir /tmp/dbttest`** — per riprodurre il bug del job senza alterare il profilo
   reale: un profilo temporaneo in `/tmp`, costruito copiando `dev` e togliendo il `catalog`.
   Effimero e isolato; il run fallito non crea tabelle.

**Pulizia post-test:**
```sql
drop table if exists workspace.bronze_silver.ais_clean;  -- tabella dev del test #5
```
```bash
rm -rf /tmp/dbttest   # profilo temporaneo del test #6
```

---

## Lezione / cosa fare la prossima volta

1. **Su un dbt_task di Databricks, il `catalog` NON arriva dal tuo `~/.dbt/profiles.yml`.**
   Databricks genera il profilo (target `databricks_cluster`). Se non gli dici il catalog,
   il default di sessione è `hive_metastore` (disabilitato in Free Edition). **Imposta sempre
   `catalog` e `schema` nel `dbt_task`** dentro `databricks.yml`.
2. **Pinnare le relazioni (`+database`/`database`) non basta.** Copre i nomi delle tabelle,
   non il default di sessione usato da creazione-schema/metadata. Servono entrambe le cose
   (relazioni pinnate **+** catalog di sessione).
3. **Riproduci prima di rifixare.** Un profilo temporaneo in `/tmp` senza catalog ha
   trasformato un "tiro a indovinare" in una **certezza** in 2 minuti.
4. **Testa eseguendo davvero, ma in sandbox:** target `dev` (schema isolato) + finestra vuota
   (0 righe). Cattura i bug che `parse`/`compile` non vedono (sintassi a runtime, default di
   sessione) senza rischi e senza costi.
5. **Errori che `parse` e `compile` NON prendono:** SQL renderizzata invalida (il bug Jinja) e
   il default-catalog di sessione. Solo un'**esecuzione** contro il warehouse li rivela →
   vale la pena di un `dbt run` no-op/sandbox in CI.
6. **Attenzione al race merge→deploy→run:** la deploy action parte sul push a `main` e impiega
   qualche minuto. Rilanciare il job prima che la action sia **verde** esegue ancora il codice
   vecchio. Aspetta il verde, poi `databricks bundle run`.

---

## Comandi di riferimento utili

| Scopo | Comando |
|---|---|
| Profilo locale sano? (catalog, connessione) | `dbt debug` |
| Verifica statica (no warehouse) | `dbt parse` · `dbt compile --select <m> --vars '{...}'` |
| Cosa risolve la relazione/source? | `grep "from " target/compiled/.../<m>.sql` |
| Test reale ma sandbox (dev, 0 righe) | `dbt run --select <m> --vars '{"start_date":"2023-01-01","end_date":"2023-01-01"}'` |
| Riprodurre la condizione del job (no catalog) | profilo temp in `/tmp` senza `catalog` + `dbt run --profiles-dir /tmp/dbttest --debug` |
| Vedere le statement eseguite | aggiungi `--debug` al `dbt run` |
| Validare il bundle dopo modifiche a `databricks.yml` | `databricks bundle validate --target prod` |
| Deploy + run del job | `databricks bundle deploy --target prod` → `databricks bundle run ais_dbt --target prod` |
