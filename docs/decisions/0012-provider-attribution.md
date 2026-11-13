# ADR-0012: The attribution of provider data travels with the data, from the rain table to every export

- Status: accepted (the author's order of 2026-11-13: every product with IMGW-PIB data
  carries the attribution its terms require); amended 2026-11-13 by Nogat ECO-065 (see
  Amendment)
- Date: 2026-11-13
- Requirements: Nogat DEV §20 and ECO-060 (fields `attribution` and `terms_notice`, the
  file forms of DEV-20.5, the order of the lines); AGI-4.1 (an optional field keeps the
  version of a document)

## Context

`rainfall build` takes the PMAXTP depth of IMGW-PIB (from the document of `obserwator
pmaxtp fetch --json` or through Obserwator for a point). PMAXTP has terms of its own, the
„Regulamin udostępniania danych projektu PMAXTP” (<https://klimat.imgw.pl/opady-maksymalne>):
ust. 1 asks for the source with the address of the page and the citation of the
monograph of the project, ust. 2 for the mark of processed data. A design rain made from
a quantile is processed data, and so is everything made from it: the model, the run, the
flood maps and the station series. A product with them also links the terms that apply,
so its reader finds the conditions of use at the provider.

Before this decision only the result of `rainfall build` had a notice (`pmaxtp_attribution`,
an English sentence pointing at the general terms of danepubliczne.imgw.pl). The rain
table, the model directory, the run and the exports said nothing.

## Options considered

| Option | Verdict |
|---|---|
| A. The lines travel with the data: the fields `attribution` and `terms_notice` of every result document made from provider data, the trailing CSV columns of the same names, `ATTRIBUTION.txt` in a model, run or network-run directory, GeoTIFF tags of the same names; each command reads what its inputs carry and passes the union on | Chosen |
| B. Only the result documents carry the lines | Rejected: the files are the products that are handed on; a flood map without the lines breaks the terms |
| C. Comment lines (`#`) before the header of a CSV table | Rejected: DEV-20.5 fixes trailing columns for every tool, and Hydrolog's tables use them |
| D. Keep the notice of `rainfall build` | Removed: it named the wrong terms and reached no file |

## Decision

Option A. `hydraulik.attribution` holds the texts, verbatim and Polish (PS, PP and the
monograph M; the terms line RK of DEV-20), and the forms:

- `rainfall build` gives a PMAXTP rain the PMAXTP lines, merged with the `attribution`
  and `terms_notice` of the Obserwator document; a Hydrolog hyetograph document passes
  its own lines on; a depth you give carries none.
- The rain table has the columns `attribution` and `terms_notice` after `depth_mm`, one
  line per cell from the first row down, the rest joined with newlines into the last
  cell of a short table; the readers take the value columns by name.
- `model build` reads them from the rain table and writes `ATTRIBUTION.txt` (the
  attribution, then the notice, one line per line).
- `model run` and `model couple` copy it to the output directory; `model couple` and
  `swmm run` add the lines of the inflow table (Hydrolog's `route network` tables).
- A write of `ATTRIBUTION.txt` to a directory that has one merges into it (Nogat
  DEV-20.5, 6f75180): each line once, in the order of DEV-20.4 and DEV-20.7; it needs no
  `--force` (the plain writer's `merged` targets), and when the lines add nothing the
  file is not written at all (a run into the model directory).
- `results read` and `results export` read `ATTRIBUTION.txt` beside the map; the export
  writes the trailing CSV columns or the GeoTIFF tags.
- The documents `hydraulik-rain/1`, `-model/1`, `-run/1`, `-results/1`, `-export/1`,
  `-swmm/1` and `-couple/1` have the two fields; both are empty without provider data. The
  version stays `/1` (an optional field, AGI-4.1).

In `ATTRIBUTION.txt` the terms lines are recognised by their form, „Regulamin <whose
terms>: <address>” (DEV §20), so one file holds both lists.
Lines merged from several inputs are kept once each, the lines of DEV-20 in the order of
DEV-20.4 and DEV-20.7 (S, P, PS, PP, M, C, CP; RD, RH, RK), any other line after
them.

## Consequences

- A product made from a PMAXTP depth carries the lines in every file Hydraulik writes;
  whoever publishes it has the text to print.
- A model rebuilt into a directory that had `ATTRIBUTION.txt`, from a rain without
  provider data, keeps the old file; a rain with provider data adds its lines to it.
  More attribution than needed, never less.
- `terrain download` keeps its `sources` (GUGiK, ISRIC): those providers are not under
  DEV §20.

## Amendment (2026-11-13, Nogat ECO-065)

Nogat ECO-065 („Tam, gdzie się da, odsyłamy do regulaminu dostawcy danych; treści w
naszych produktach ograniczone do minimum”) dropped the line H and the sentence N, which
restated the IMGW-PIB terms, and renamed the terms lines after the terms they open: RD
„Regulamin danych IMGW-PIB: https://danepubliczne.imgw.pl/regulations”, RH „Regulamin
serwisu hydrologicznego IMGW-PIB: https://hydro.imgw.pl/#/regulamin”, RK „Regulamin
danych PMAXTP: https://klimat.imgw.pl/opady-maksymalne”. This record says so above. In
Hydraulik:

- `hydraulik.attribution` has no `IMGW_TERMS_NOTICE`; a PMAXTP product carries RK alone in
  `terms_notice`, and the terms lines are recognised by the new form instead of the
  sentence N and the prefix `Regulamin: `.
- Lines that older producers and files still hold are read as DEV-20 has them now: H and
  N are dropped, and the three old terms lines `Regulamin: <address>` of RD, RH and RK
  are read as their new form; any other line of the old form is dropped too. Hydraulik
  takes every line from its inputs, so this is where the old lines stop.
- A model, run or network-run directory written before keeps the old lines in its
  `ATTRIBUTION.txt` until a later write to it: that write replaces the file without them,
  even when it adds no line. The commands that read the directory (`model run`, `model
  couple`, `results`) carry only the new lines on; the file needs no rebuild by hand.
- Exports already handed out (CSV, GeoTIFF) keep the lines they had.
