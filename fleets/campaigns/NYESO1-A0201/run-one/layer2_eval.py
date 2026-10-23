"""Legacy container entrypoint: writes ``layer2_results.json`` via ``layer2_core``.

Kept for the pinned ghcr / Modal path (`/artifacts`). Prefer ``layer2_orchestrator.py``
for the full bundle (Tier 0 + item 10 + provenance).
"""
import json
import os
import sys
from pathlib import Path

# Container layout: worker copied under /src; local runs use this directory.
for candidate in ("/src", str(Path(__file__).resolve().parent)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import layer2_core  # noqa: E402

root = Path(os.environ.get("LAYER2_ARTIFACTS", "/artifacts"))
out: dict = {}
for d in sorted(root.iterdir()):
    if not d.name.startswith("pres_") or not d.is_dir():
        continue
    paths = layer2_core.design_paths(d)
    if paths["cif"] and paths["pae"]:
        out[d.name] = layer2_core.score_ipsae_record(
            d.name, paths["cif"], paths["pae"], paths["metrics"]
        )

out_path = root / "layer2_results.json"
out_path.write_text(json.dumps(out, indent=1, sort_keys=True))
print(json.dumps(out, indent=1, sort_keys=True)[:200])
print("WROTE", len(out), "->", out_path)
