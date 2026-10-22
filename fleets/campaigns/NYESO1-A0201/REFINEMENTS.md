# REFINEMENTS - what the Tier 0 measurements changed

**Version:** 1.0 - **Date:** 2026-10-22 (Australia/Sydney)
**Status:** findings and proposals. **No gate in `FLEET.toml` is changed by this document.**
Every proposal here needs the user's decision, exactly as `UPGRADES.md` requires of its own
section 4.

`UPGRADES.md` is the methods half of the geometric layer, and it was written before its own
Tier 0 items had been run. This file records what happened when they were run on the ten
run-one designs, and refines the campaign on that evidence. It adds no measurement to
`CONTACTS.md` and removes none.

Artifacts: `run-one/tier0_targeting_results.json`, `run-one/shell_sweep_results.json`.
Code: `run-one/tier0_targeting.py`, `run-one/shell_sweep.py`. Flags: `targeting_flags.json`.

---

## F1 - Item 1 is vacuous at the 10 A shell, as G7 predicted

Off-epitope contact fraction across all ten designs at the inherited 10.0 A shell:
**0.000 to 0.111, median 0.025, five designs at exactly zero**. The shell holds 66-73
target residues, 57-64 of them on chain A - most of the groove floor and both helices.

That is not a good score, it is a non-measurement. A binder sitting anywhere on the peptide
strip scores as fully on-epitope by construction, and one drifting onto the helices would
score the same. G7 Limits called it in advance: "at 10 A on a small target a shell can
swallow most of the surface, making off-epitope vacuous". It is now measured, not feared.

**A threshold cannot be pre-registered on a statistic with no spread.** Item 1 cannot become
a gate at 10 A whatever value is chosen.

### The sweep

`run-one/shell_sweep.py` asks only the prior question: is there a cutoff at which item 1
discriminates at all?

| shell A | median | range | sd | designs at 0 | shell size |
|---|---|---|---|---|---|
| 4.0 | 0.458 | 0.125-0.611 | 0.132 | 0 | 16-21 |
| 5.0 | 0.316 | 0.125-0.474 | 0.093 | 0 | 21-23 |
| 6.0 | 0.257 | 0.000-0.421 | 0.109 | 1 | 27-32 |
| 7.0 | 0.194 | 0.000-0.278 | 0.081 | 1 | 35-43 |
| 8.0 | 0.065 | 0.000-0.167 | 0.059 | 3 | 46-53 |
| 10.0 | 0.025 | 0.000-0.111 | 0.037 | 5 | 66-73 |
| 12.0 | 0.000 | 0.000-0.111 | 0.037 | 6 | 86-91 |

Spread collapses monotonically as the shell widens. Discrimination survives at 4-6 A and is
effectively gone by 8 A.

### Proposal P1, and the trap inside it

**Proposed:** re-register item 1 at a **5.0 A** shell, RECORDED-NON-GATING through run two.
Consider gating only once a second run exists to calibrate against.

**The structural argument, which is what must carry it.** 5.0 A is about one contact shell
beyond the hotspot atoms. It admits the groove rim a binder must touch to reach the peptide
and excludes the helix flanks it need not touch, so the quantity measures what its name
claims. At 10 A the name no longer matches the quantity.

**The trap.** The sweep must NOT be read as "pick the cutoff with the most spread". That
fits a free parameter to this campaign own ten designs, which is the circularity
UPGRADES.md section 5 rejects for Sc. The sweep establishes only that 10 A cannot work and
that a usable range exists. The 5.0 A choice stands or falls on the structural argument
above; the sweep merely shows it is not vacuous.

---

## F2 - Item 3 holds, and it is the signal that carries information

Zero buried-anchor contacts in all ten designs, reproduced independently of
`contact_analysis.py` by the G7 code path. Coldspot contact is ~0 throughout: one residue in
two designs, 0.005 of the declared coldspot set.

This matters because of what run one did and did not constrain. The submitted request named
all nine peptide residues in `epitope_residues`, so the peptide-directed footprint is
substantially our own specification returned to us. The anchor result was never specified
and is real geometry. **Item 3 is the one Tier 0 quantity whose run-one value is independent
evidence**, and it is also the cheapest. It should be gated first, not last.

**Proposed P2:** adopt item 3 as a GATING pass/fail at exactly zero, since any non-zero value
is a mis-modelled pose rather than a weak design. This is the only Tier 0 item whose
threshold needs no calibration: zero is forced by the geometry, not transferred from a
teacher.

---

## F3 - Section 6 of UPGRADES.md contradicts itself, and the data lands on the seam

Measured Spearman for `iptm` against invariant-surface fraction (item 4) is **+0.636**
(n = 10; **+0.500** excluding the `pres_xpto8wJvfrJQhLVH4Mvz` outlier). Positive: higher
interface confidence goes with MORE invariant-surface burial.

Section 6 states two things that cannot both hold:

- Its **falsification criterion** says the prediction is wrong if high-`iptm` designs show
  *low* invariant-surface use. Under that reading +0.636 leaves the prediction standing.
- Its **operational line** says to expect `iptm` rank order to *anti-correlate* with item 4.
  Under that reading +0.636 contradicts it.

Item 4 is a lower-is-better quantity, so "high affinity, less selective" implies a POSITIVE
`iptm`-to-item-4 correlation. The falsification criterion is consistent with the physical
argument in section 6 and with section 2; the operational line appears to be the slip.

**Proposed P3:** correct the operational line in `UPGRADES.md` section 6 to expect positive
correlation with item 4, keeping the anti-correlation expectation for item 8 where it does
apply. **Owner decision - the prediction is pre-registered and only the user may restate it.**
Until it is restated, nothing should be scored against section 6.

Caveats that travel with the +0.636: n = 10, predicted coordinates, one campaign, and item 8
is not computed, so the affinity-selectivity tension itself remains untested.

---

## F4 - The coldspot rim is still undefined

UPGRADES.md names "the alpha1/alpha2 rims" as coldspot but the rim is defined nowhere in the
repository. `targeting_flags.json` currently implements it as helix-minus-shell, which makes
the coldspot set depend on the shell cutoff - so P1 would move it too. The alternative is an
explicit rim residue list from the published TCR-footprint literature, which would be
independent of the cutoff.

**Proposed P4:** declare an explicit rim list rather than deriving it, so items 1 and 2 stop
sharing a free parameter. Not done here: it needs a literature decision, not a code change.

---

## Decisions this document needs

| # | Decision | Blocked on |
|---|---|---|
| P1 | Shell cutoff for item 1: 5.0 A proposed, non-gating through run two | user |
| P2 | Adopt item 3 as a gate at exactly zero | user |
| P3 | Restate the section 6 operational line | user, pre-registered |
| P4 | Explicit alpha1/alpha2 rim residue list | user + literature |
| - | Items 5, 7, 8, 10 remain GATING-proposed and untouched here | user |

Unchanged by this document: `FLEET.toml`, the APPR human gate, `spend_cap_usd = 15.00`,
`on_deny = "HALT"`, the OD-8 digest resolution, and the gating descriptors `iptm` and
`plddt`. The MAGE-A3 / titin record in `CASE.md` and `UPGRADES.md` is retained deliberately.
