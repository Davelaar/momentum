
Opdracht 10a — OTO/OCO orkestratie + BE-move
--------------------------------------------
- Bouwt een OTO-plan: ENTRY → SL → TP-legs (geen exchange-OCO; orkestratie in code).
- Duplicate-protectie via `var/exec_history.json` + `cl_ord_id` registry (idempotent).
- Na (gesimuleerde) TP1-fill wordt SL naar BE(+offset) geamendeerd (simulate-pad).

CLI:
  # Alleen plan tonen
  python -m momentum.scripts.exec_oto_plan --pair BTC/USD --qty 0.01 --entry 25000 --tp1 25500 --tp1-ratio 0.4 --tp2 26000 --tp2-ratio 0.6 --sl 24500 --be-offset 5 --validate 1 --execute 0

  # Plan uitvoeren met validate=1 (broker-dryrun) en BE-move simuleren
  python -m momentum.scripts.exec_oto_plan --execute 1 --simulate-partial 1

Opmerking:
- Live BE-amend via WS v2 'replace' hangt af van broker-ondersteuning; hier stubben we 'replace' in `extras`.
- In de echte live-loop koppel je TP-fills via private WS fills/events om BE-move automatisch te triggeren.
