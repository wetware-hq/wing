# Layer 2 entry (specificity campaign)

Run from the parent run-one directory (mirrored artifacts):

```bash
cd ../NYESO1-A0201/run-one
python3 layer2_orchestrator.py --specificity-campaign \
  --artifacts ./artifacts \
  --decoy-panel ../../NYESO1-A0201-specificity/decoy_panel.yaml \
  --panel-out ../../NYESO1-A0201-specificity/panel.example.json
```

Decoy refolds must appear under `artifacts/decoy_refolds/<design_id>/<decoy_id>/` before
`specificity_margin` is non-null.
