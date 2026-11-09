# Request v3 frozen-backbone arm — 2026-11-09

Actual single-arm training authorized; source/config handoff before launch.
Runtime status is authoritative. Run `request-v3-frozen-backbone-20261109-r1`.

[Precommitted design and all31feature indices/names](../ai-training/configs/research/request-v3-frozen-backbone-20261109.json).

Original v2 parameters/biases are read-only and hash checked every update. A
separate31x64 tensor, no adapter bias, owns the entire1,984parameter optimizer.
No original gradient arrays are constructed. No original parameters enter AdamW.

Schema rule: use all6count buckets+17punctuation counts+8syntax flags, body indices
15..45/input indices603..633. Exclude11state+4media indicators/input588..602,
which have no tensor and contributezero. Membership is label/score-free; experiment
motivation and exposed DEV/body cohorts make conclusions exploratory.

Same frozen236release,48eligible TRAIN/42canonical views, group order/seed17,
batch16,60updates/20epochs, partial-binary smoothing0.005,familyweight0. Fresh
AdamW lr0.0001/decay0.0001/clip1 on adapter only. No raw data/label changes, new
requests, CAL/DEV/body gradients or fitted normalization statistics.

Intentional implementation differences from full finetune: clip/moments/decay
operate only in the trainable subspace; first layer is original588FP64affine
rounded plus separate31FP64affine rounded, summed inFP32. Original remaining
layers/activations unchanged. This preserves baseline score bytes atzero adapter
orzero selectedtail; it is not a secretly changed learning-rate search.

Prepare verified parameter/dimension/loss/gradient compatibility and zero-adapter
byte parity on42TRAIN views and154non-OK feature-only probes, plus explicit GET
checks. Full46body vector is not assumedzero: state/media remain present, selected
31tail iszero per existing blank/validator contract. No intent/method-based gate.

Actual step1 will be checkpointed/reloaded and resumed in another process, within
the same60update budget. Existing atomic checkpoint writer retained; adapter loader
stores onlyA/m/v plus sampler/RNG/scheduler and binds original backbone hashes.
Latest corruption is reported; verified previous generation is available, no
silent optimizer reset. Final-budget checkpoint alone is evaluated.

Four arms: v2,existing calibration-only,previousfull-v3step60,new adapter. New
adapter threshold strictlygreater than maximum of11eligible CALbenign scores.
Original v2threshold is a predeclared secondary operatingpoint, not selected from
DEV/body results. Zero-body score parity and fixed-original-threshold parity are
separate from operating-point changes due to new calibration.

Research screen locked: preservedbackbone/zero-bodyparity; at CALpoint >=2of4body
XSSdetections,0of4bodyFP and no additional benignFP on90DEV. Otherwise CASEB;
integrity/parityfailure CASEC. No independentquality claim or promotion. Predeclared
inference ablations disable entireadapter/counts6only/syntax25only.

Private run:
`ai-training/.artifacts/request_v3_frozen_backbone_20261109/request-v3-frozen-backbone-20261109-r1/`.
`status.json`, `loss.jsonl`, `model/`, `resource/`, `completion.json`,
`supervisor-result.json`, `evaluation/` hold authoritative execution evidence.
Supervisor `idps-request-v3-frozen-backbone-20261109-r1.service` uses existing
independent resource guard, initial25%onecore/2GiB/noSwap/4GiBreserve,
rolling80°C/instant85°C. No automatic retry, extra arm, capture or deployment.
