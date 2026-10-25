# ADR-0009: A hydrograph enters one node of the coupled network, and the balance has a term for it

- Status: accepted (delegated approval of the plan, 2026-10-24; the coupling stays an
  optional feature, never a requirement of `model build` or `model run`)
- Date: 2026-10-25
- Requirements: ADR-0002, ADR-0005, AGI-1.2 (the option names of `swmm run`)

## Context

`hydrolog route network --output-dir DIR` writes `<id>.csv` (`time_min,discharge_m3s`, a
regular step) for every node of a river network. Hydrolog's INTEGRATION.md calls it the
hand-off to Hydraulik and a reader in Hydraulik a `request` issue. `swmm run` reads that
table already (`--inflow`, `--inflow-node`) and a fixture made by the real command now
proves it (`tests/fixtures/hydrolog`). `model couple` could not take it: the water that
comes from a catchment outside the grid and enters the sewer had no place in the coupled
run. The plan (steps 12 and 13) did not call for it; the coordinator asked for it.

## Options considered

| Option | Verdict |
|---|---|
| A. `--inflow` and `--inflow-node` for `model couple`, as in `swmm run`; the loop takes a mapping from node to a series and adds its discharge to the exchange of that node | Chosen |
| B. Put the hydrograph into the generated SWMM input (`[INFLOWS]` with a time series) | Rejected: the input is dated and a user's own input has its own clock; the loop sets the lateral inflow of every node each interval anyway and has to know the volume it gave |
| C. A discharge point of SFINCS (`srcfile`, `disfile`): the water enters the surface | Not built: another flow path (a river entering the 2D domain) with another term in the balance (`inflow_m3` exists and is 0 today); a question for the author |
| D. Several inflows by repeating the option | Not built: the library takes a mapping (`couple(..., inflows)`), the command takes one as `swmm run` does; repeating the option can be added without changing anything else |

## Decision

Option A (`hydraulik.coupling.coupler`, `hydraulik.coupling.worker`,
`hydraulik.operations.couple`).

- **Names and time.** The options are those of `swmm run`. The time of the table is time
  from the start of the model run, as in the rain table. What lies beyond the end of the
  run is cut (the notice `inflow_cut`, as in `swmm run`); a table that starts late is zero
  before its first time.
- **One call.** SWMM takes the lateral inflow of a node as its rate (`add_inflow`
  replaces the value). At an exchange node the loop gives `taken / length + discharge` in
  one call; at any other node of the network (outside the domain, or a junction of your
  input without `[COORDINATES]`) it gives the discharge alone.
- **The middle of the interval.** The discharge is read at the middle of each interval, as
  `run_swmm` does for a stride: a line is integrated exactly, and a table whose knots fall
  on the boundaries of the intervals gives its own volume. The volume given to each node
  is booked (`CouplerResult.inflows_m3`) and the result's `coupling.inflow` has the file,
  the node, the volume of the table and the volume given.
- **The balance.** `network_inflow_m3` is a term of its own: it enters the network, not the
  surface (`inflow_m3` stays the surface's). The network side is `exchanged +
  network_inflow - pending - network - outfall - lost`, and the percentage is that of the
  water that entered including it; without the term a dry surface has no denominator and
  its residual could never be flagged.
- **Checks before any step.** `--inflow` and `--inflow-node` go together (`missing_option`);
  the table is read (`invalid_hydrograph`, `path_missing`); the node is a junction of a
  network table (its outfall takes no inflow) or any node of your SWMM input
  (`unknown_node` lists the names); the loop refuses a node the network does not have
  before the first step. `--check` names the step and says when the table is cut.

## Evidence

The table of the node OUT of the fixture: 279 m3, peak 0.175 m3/s at 25 min, 70 min
long. A bowl of 20 x 20 cells of 5 m with no rain and a manhole with a 0.15 m pipe (it
carries 0.026 m3/s at most), 75 min, both local builds of SFINCS:

| Run | Given | Net from network to street | Left on the street | Out of the outfall | Error | Remarks |
|---|---|---|---|---|---|---|
| v2.4.1 (`ms`) and `main` (`m3s`), 5 s | 279.0 m3 | 164.6 m3 | 164.6 m3 | 110.7 m3 | -0.65 m3 (-0.23 %) | same digits on both; 0.44 m deepest; 925 m2 deeper than 0.1 m; 31 sign flips (notice); 16 s and 23 s |
| `main`, 1 s | 279.0 m3 | 166.7 m3 | 166.7 m3 | 110.7 m3 | -0.65 m3 (-0.23 %) | 0.43 m deepest; 3 sign flips, no notice; 81 s |
| `main`, coordinator, 2 s | 279.0 m3 | 151.7 m3 | 151.7 m3 | 123.8 m3 | +1.7 m3 (+0.60 %) | SWMM continuity error 1.3 % (SLOT); 75 sign flips; 56 s |

The error of the first two runs is SWMM's own continuity error (-0.028 % of its inflow);
the surface side closes to 0.0 m3 in all three. The first spill reaches the street
between 240 s and 600 s, as the table says it must (it delivers 2.3 m3, the volume of
the manhole, after 250 s).

## Consequences

- `external_inflow_m3` of SWMM in a coupled run is the hydrograph plus the net exchange
  with the surface (negative where the network spilled); `balance.network_inflow_m3` is
  the hydrograph alone.
- A manhole that floods returns water to the street, and the street gives it back when
  the pipe has room: `flooded_m3` of a node is a gross volume (2258 m3 for 279 m3 of
  hydrograph at 5 s), and the net is `exchanged_m3`. The oscillation notice at 5 s says
  what to do, and the 1 s run shows that it works.
- The rain of the catchment that the hydrograph came from must not be given to the surface
  as well; the rules of the command say so.
- The hand-off needs no `request` issue in Hydraulik: the table is the one `swmm run` read
  before, nothing of Hydrolog is imported, and the format is held by a fixture made by the
  real command and a live test that makes it again.
