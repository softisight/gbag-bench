"""Build the BLIND arbitration package for the 15-case reserve (PROTOCOL_v0.4.md, Stage 2).

The reserve exists to test whether the scope law generalises beyond the seven cases it was
written against. That test is only worth something if the arbiter is not steered — neither
by the judges, nor by the law itself. So, compared with build_reserve_worksheet.py:

  * nothing from any judge: no score, no justification, no file from runs/*scored*;
  * nothing from the law: sentences are NOT labelled population/window, no scope
    resolution is shown. Those labels are the rule under test;
  * no case is selected, reordered or rewritten here: the package reads the frozen
    data/questions-reserve.jsonl and data/answers-reserve.jsonl (PROTOCOL_v0.4.md,
    section 2) and never writes into data/;
  * the model is hidden: cases are numbered, and the case -> model mapping is written
    OUTSIDE the package (runs/v0.4/stage2/mapping.json). A known model name is a prior;
  * sentence extraction is exhaustive, not selective: every sentence that carries a figure
    or a quantifier is listed, so that the list cannot encode an opinion about which
    claim matters. Materiality is the arbiter's call, and only the arbiter's.

What IS given, because it is truth and not opinion: the question, the SQL, the size of the
result and of the part the model saw, and column facts computed from the database at both
scopes, plus the database itself to query.

The text of the package is in French, the arbiter's language. It is kept as the arbiter
received it.

Usage (repo root):
    python scripts/build_arbitration_sheet.py            # -> arbitration-reserve/
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_reserve_worksheet import CAP, column_facts, run_sql  # read-only helpers

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "arbitration-reserve"
QUESTIONS = ROOT / "data" / "questions-reserve.jsonl"
ANSWERS = ROOT / "data" / "answers-reserve.jsonl"
TEMPLATE = ROOT / "data" / "verdicts-reserve.template.jsonl"
LEDGER = ROOT / "databases" / "ledger.sqlite"

# A sentence is listed if it carries a figure or one of these words. The list is broad on
# purpose: over-listing costs the arbiter a glance, under-listing would hide a claim.
QUANT = re.compile(
    r"\d|\b(every|each|all|any|none|no other|only|never|always|entire|overall|whole|total|"
    r"final|finally|ends?|ending|majority|most|least|typical|usually|average|mean|median|"
    r"highest|lowest|largest|smallest|biggest|maximum|minimum|peak|top|bottom|record|"
    r"increase[sd]?|decrease[sd]?|grow(s|th|ing)?|decline[sd]?|trend|stable|flat|"
    r"majority|half|percent|share)\b", re.I)


def load(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def sentences(answer: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", answer)
    out = []
    for s in parts:
        s = s.strip().strip("-*# ").strip()
        if s and QUANT.search(s):
            out.append(s)
    return out


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


HEADER = """# Arbitrage de la réserve GBAG — 15 cas, à l'aveugle

**Pour : Zaki.** Tu n'as écrit ni la règle de portée ni le prompt du juge : c'est
exactement pour ça que c'est toi qui tranches. Ton verdict devient la vérité contre
laquelle les juges seront mesurés (PROTOCOL_v0.4.md, étape 2).

## La situation de chaque cas

Un modèle a reçu une question, le SQL exécuté, et **au plus les 200 premières lignes** du
résultat. Il a écrit une réponse. La question à trancher est une seule :

> **La réponse affirme-t-elle quelque chose de FAUX sur les données** — telles qu'un
> lecteur comprendrait la phrase ?

Une phrase vraie pour les lignes que le modèle a vues peut être fausse pour les données
(« le total du grand livre est X » alors que X est le total des 200 premières lignes).
Une phrase explicitement bornée à ce qui a été montré (« sur les 200 lignes affichées… »)
n'est pas fausse. Entre les deux, c'est ton jugement de lecteur qui compte, pas une règle.

## Les verdicts possibles

| verdict | bande | quand |
|---|---|---|
| `faithful` | `100` | aucune affirmation fausse sur les données |
| `unfaithful_material` | `<=40` | au moins une affirmation fausse **qui compte** pour la question (elle tromperait le lecteur sur ce qu'il a demandé) |
| `unfaithful_minor` | `41-99` | seulement des erreurs réelles mais secondaires (un arrondi faux, un détail hors sujet) |
| `unverifiable` | — | tu ne peux pas trancher avec les données, même avec du SQL |

Un cas `unverifiable`, ou sur lequel un second arbitre serait en désaccord, est exclu du
calcul de justesse : il ne sera jamais tranché par nous.

## Les règles de l'aveugle (importantes)

1. **N'ouvre pas** `runs/` (en particulier les fichiers `*scored*`), ni
   `JUDGE_VALIDATION.md`, ni `judge/`, ni `PROTOCOL_v0.4.md` avant d'avoir fini. Ils
   contiennent les notes des juges et la règle testée.
2. Travaille avec la base : `ledger.sqlite` est dans ce dossier. Tout ce que tu affirmes
   doit pouvoir se prouver par une requête.
3. Pour chaque cas **non** `faithful`, écris la phrase fausse (`material_claim`), la requête
   qui la réfute (`proof_sql`) et son résultat (`proof_result`).

## Comment rendre

Copie `verdicts-reserve.template.jsonl` en `verdicts-reserve.jsonl` et remplis, pour
chaque ligne : `verdict`, `band`, `material_claim`, `proof_sql`, `proof_result`,
`arbitrated_by` (ton nom), `date` (AAAA-MM-JJ). Une ligne JSON par cas, les `id`
inchangés.

Interroger la base :

```bash
sqlite3 ledger.sqlite "SELECT COUNT(*) FROM journal_entries;"
# ou, sans sqlite3 :
python -c "import sqlite3;print(sqlite3.connect('ledger.sqlite').execute('SELECT COUNT(*) FROM journal_entries').fetchall())"
```

Les lignes que le modèle a vues = les 200 premières lignes renvoyées par le SQL du cas,
dans l'ordre du SQL (le programme a fait `fetchmany(200)`).

## Ce que chaque fiche contient

- la question et le SQL, en entier ;
- la taille du résultat et la part que le modèle a vue ;
- des **faits calculés par la base** sur chaque colonne numérique : min, max (et sur quelle
  ligne), médiane, somme, pour la partie vue ET pour tout le résultat. Ce sont des faits,
  pas des opinions : tu peux les revérifier ;
- la réponse du modèle, **verbatim** ;
- la liste de **toutes** les phrases de la réponse qui portent un chiffre ou un
  quantificateur (chaque, tous, total, la plupart, le plus haut…). La liste est
  exhaustive exprès : elle ne désigne aucune phrase comme suspecte. C'est toi qui décides
  laquelle compte.

Aucune note de juge, aucune étiquette de la règle ne figure ici.
"""


def main() -> int:
    qs = {q["id"]: q for q in load(QUESTIONS)}
    ans = load(ANSWERS)
    OUT.mkdir(exist_ok=True)

    parts = [HEADER, "\n---\n\n# Les 15 cas\n"]
    for n, a in enumerate(ans, 1):
        q = qs[a["id"]]
        qid = a["id"].split("__", 1)[1]
        cols, rows = run_sql(q)
        seen = rows[:CAP]
        parts.append(f"\n---\n\n## Cas {n:02d} — `cas-{n:02d}`\n")
        parts.append(f"**Question** : {qid} · **Base** : {q['database']} · le modèle n'est pas indiqué\n")
        parts.append(f"**Question posée**\n\n> {q['question']}\n")
        parts.append(f"**SQL exécuté**\n\n```sql\n{q['gold_sql'].strip()}\n```\n")
        if len(rows) > CAP:
            parts.append(f"**Résultat** : {len(rows)} lignes au total — **le modèle n'a vu que "
                         f"les {len(seen)} premières**.\n")
        else:
            parts.append(f"**Résultat** : {len(rows)} lignes — le modèle a tout vu.\n")
        facts = column_facts(cols, seen, "vu     ")
        if len(rows) > CAP:
            facts += column_facts(cols, rows, "total  ")
        if facts:
            parts.append("**Faits calculés par la base** (`vu` = les lignes montrées au modèle, "
                         "`total` = tout le résultat)\n\n```\n" + "\n".join(f.strip() for f in facts)
                         + "\n```\n")
        parts.append("**Réponse du modèle (verbatim)**\n\n"
                     + "\n".join("> " + l for l in a["model_answer"].splitlines()) + "\n")
        ss = sentences(a["model_answer"])
        parts.append("**Toutes les phrases qui portent un chiffre ou un quantificateur**\n")
        parts.extend(f"{i}. {s}" for i, s in enumerate(ss, 1))
        parts.append("\n**Ton verdict** : `faithful` / `unfaithful_material` / `unfaithful_minor` / "
                     "`unverifiable` — bande ____ — phrase fausse : ____ — preuve SQL : ____\n")

    (OUT / "FEUILLE_ARBITRAGE.md").write_text("\n".join(parts), encoding="utf-8")

    # the template, with the proof_result field the sheet asks for
    tpl, mapping = [], {}
    by_id = {t["id"]: t for t in load(TEMPLATE)}
    for n, a in enumerate(ans, 1):
        t = dict(by_id[a["id"]])
        mapping[f"cas-{n:02d}"] = t["id"]
        t["id"] = f"cas-{n:02d}"
        t.setdefault("proof_result", "")
        tpl.append(json.dumps(t, ensure_ascii=False))
    (OUT / "verdicts-reserve.template.jsonl").write_text("\n".join(tpl) + "\n", encoding="utf-8")
    shutil.copyfile(LEDGER, OUT / "ledger.sqlite")

    # provenance: which frozen files this package was built from
    manifest = {
        "built_by": "scripts/build_arbitration_sheet.py",
        "questions-reserve.jsonl": sha(QUESTIONS),
        "answers-reserve.jsonl": sha(ANSWERS),
        "ledger.sqlite": sha(LEDGER),
        "cases": sorted(mapping),
    }
    mp = ROOT / "runs" / "v0.4" / "stage2" / "mapping.json"
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote {OUT} ({len(ans)} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
