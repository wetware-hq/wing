import json, sys, os
import numpy as np
sys.path.insert(0, "/src")
from bindi.ipsae import score_from_paths, parse_predicted_cif, TokenAlignmentError

root = "/artifacts"
out = {}
for d in sorted(os.listdir(root)):
    p = os.path.join(root, d)
    if not d.startswith("pres_") or not os.path.isdir(p):
        continue
    rec = {}
    cif = os.path.join(p, f"{d}_predicted.cif")
    pae = os.path.join(p, "pae.npz")
    mj = os.path.join(p, "metrics.json")
    rec["has_cif"] = os.path.exists(cif); rec["has_pae"] = os.path.exists(pae); rec["has_metrics"] = os.path.exists(mj)
    m = json.load(open(mj))
    rec["iptm"] = m.get("iptm"); rec["complex_plddt_metrics_json"] = m.get("complex_plddt")
    try:
        parsed = parse_predicted_cif(cif)
        by = {}
        for r in parsed.residues:
            by.setdefault(r.chain_id, []).append(r.plddt)
        allv = np.concatenate([np.asarray(v) for v in by.values()])
        rec["plddt_std_all"] = float(np.std(allv))
        rec["plddt_mean_all"] = float(np.mean(allv))
        rec["chain_mean_plddt"] = {k: float(np.mean(v)) for k, v in by.items()}
        rec["chain_len"] = {k: len(v) for k, v in by.items()}
        rec["parse_error"] = None
    except Exception as e:
        rec["parse_error"] = f"{type(e).__name__}: {e}"
    try:
        s = score_from_paths(pae, cif)
        rec["n_tokens"] = s["n_tokens"]
        rec["ipsae_ordered"] = s["ordered"]
        rec["pairs"] = s["pairs"]
        rec["min_ipsae_overall"] = min(v["min_ipsae"] for v in s["pairs"].values())
        # binder-relevant: any pair involving D
        dpairs = {k: v["min_ipsae"] for k, v in s["pairs"].items() if "D" in k.split("|")}
        rec["min_ipsae_D_pairs"] = dpairs
        rec["plddt_block"] = s["plddt"]
        rec["score_error"] = None
    except TokenAlignmentError as e:
        rec["score_error"] = f"TokenAlignmentError: {e}"
    except Exception as e:
        rec["score_error"] = f"{type(e).__name__}: {e}"
    out[d] = rec
json.dump(out, open("/artifacts/layer2_results.json", "w"), indent=1, sort_keys=True)
print(json.dumps(out, indent=1, sort_keys=True)[:200])
print("WROTE", len(out))
