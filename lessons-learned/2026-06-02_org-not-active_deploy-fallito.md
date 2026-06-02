# Deploy fallito con "Organization … cancelled or is not active yet"

**Data:** 2026-06-02
**Comando coinvolto:** `databricks bundle deploy --target prod`
**Workspace:** `7474660162002917` (Databricks Free Edition Serverless)

---

## Sintomo

Lanciando il deploy del bundle, l'upload dei file riusciva ma la creazione dei job falliva:

```
Uploading bundle files to /Workspace/Users/simone.lima97@gmail.com/.bundle/ais-anomaly-pipeline/prod/files...
Deploying resources...
Error: terraform apply: exit status 1

Error: cannot create job: Organization 7474660162002917 has been cancelled or is not active yet.
  with databricks_job.ais_dbt, ...

Error: cannot create job: Organization 7474660162002917 has been cancelled or is not active yet.
  with databricks_job.ais_ml, ...
```

Sospetto iniziale dell'utente: risorse della Free Edition esaurite. **Sbagliato.**

---

## Causa reale

L'errore **non riguarda il codice né la quota** della Free Edition. È uno **stato dell'organizzazione Databricks a livello di account**. Il messaggio ha due rami:

- `has been cancelled` → workspace cancellato (stato permanente, serve riattivazione/ricreazione)
- **`or is not active yet`** → stato **transitorio** di attivazione/riattivazione ← era questo il nostro caso

In Free Edition Serverless l'org può finire in uno stato sospeso/in-riattivazione (es. dopo inattività). In quello stato:

- **Lettura** (`jobs list`, identity, warehouse) → funziona ✅
- **Job già esistenti** → restano vivi ✅
- **Provisioning di job nuovi** (`jobs/create` via Terraform) → rifiutato ❌

Il bundle stava provando a **creare due job nuovi** (`ais_dbt`, `ais_ml`); l'unico job preesistente (`AIS Ingest Bronze`, creato in un deploy precedente quando l'org era attiva) non veniva toccato e infatti non dava errore. Questo confermava che il blocco era solo sul *create*, non sull'account in sé rotto.

---

## Come l'ho diagnosticato (comandi usati, in ordine)

### 1. Verificare a quale org/host punta la CLI e se l'utente è attivo
```bash
databricks auth describe --target prod
databricks current-user me
```
**Esito:** host e `workspace_id` corrispondevano a quello dell'errore (`7474660162002917`) → eravamo sull'org giusta. Utente `"active": true`. Quindi né host sbagliato né utente disabilitato.

### 2. Distinguere lettura vs scrittura
```bash
databricks jobs list --output json
databricks clusters spark-versions
databricks warehouses list
```
**Esito:** la lettura funzionava, esisteva 1 solo job (`AIS Ingest Bronze`, `job_id 587338635444344`), il warehouse `Serverless Starter Warehouse` esisteva (STOPPED). → Il compute c'era; il problema era solo il *provisioning di risorse nuove*. Esclusa la "quota finita".

### 3. Confermare quali job esistono già
```bash
databricks jobs list --output json | grep -E '"job_id"|"name"'
```
**Esito:** solo `AIS Ingest Bronze`. `ais_dbt` e `ais_ml` erano davvero *nuovi* → spiega perché solo loro fallivano.

### 4. Test mirato: la creazione job è bloccata adesso?
```bash
# probe: crea un job "noop" di test
cat > /tmp/testjob.json <<'EOF'
{"name":"__deploy_probe_delete_me","tasks":[{"task_key":"noop","notebook_task":{"notebook_path":"/Workspace/Users/simone.lima97@gmail.com/__nope"}}]}
EOF
databricks api post /api/2.2/jobs/create --json @/tmp/testjob.json
```
**Esito:** **SUCCESSO** → restituì `{"job_id": 687606292080974}`. Nel frattempo l'org era tornata `active`. Questo è stato il punto di svolta: la create funzionava di nuovo.

### 5. Pulizia del probe
```bash
databricks api post /api/2.2/jobs/delete --json '{"job_id":687606292080974}'
```

### 6. Rilancio del deploy
```bash
databricks bundle deploy --target prod
```
**Esito:** `Deployment complete!` — `ais_dbt` e `ais_ml` creati correttamente.

---

## Lezione / cosa fare la prossima volta

1. **`Organization … cancelled or is not active yet` ≠ codice rotto e ≠ quota Free Edition esaurita.** È uno stato dell'account Databricks.
2. **Prima diagnosi: separa lettura da scrittura.** Se `jobs list` / `current-user me` funzionano ma il *create* fallisce, il problema è il provisioning, non l'autenticazione né il tuo bundle.
3. **Non modificare `databricks.yml`** per "aggirarlo": il bundle era corretto.
4. **Se è il ramo "not active yet" (transitorio): aspetta qualche minuto e rilancia.** Si è risolto da solo in pochi minuti.
5. **Probe rapido** per capire se sei già sbloccato: crea un job noop via `jobs/create` e poi cancellalo, invece di rilanciare l'intero deploy ogni volta.
6. **Se invece persiste (>30 min) o la UI mostra un banner di sospensione** → è il ramo "cancelled" vero: vai sull'Account Console (https://accounts.cloud.databricks.com) per riattivare, o ricrea il workspace Free Edition e ri-deploya puntando al nuovo host.

---

## Comandi di riferimento utili

| Scopo | Comando |
|---|---|
| Su quale org/host sono? | `databricks auth describe --target prod` |
| Il mio utente è attivo? | `databricks current-user me` |
| Quali job esistono? | `databricks jobs list --output json` |
| Warehouse disponibili? | `databricks warehouses list` |
| La create job è sbloccata? (probe) | `databricks api post /api/2.2/jobs/create --json @probe.json` poi `.../jobs/delete` |
| Rilancio deploy | `databricks bundle deploy --target prod` |
