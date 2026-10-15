# Arikizu Technical Specification v2 (stub)

This file is a placeholder. The living specification is the v2 document
delivered separately: `Arikizu_OS_Technical_Specification_v2.md`.

Drop that file in here when you're ready to version it alongside the code.

## Reference links in the current scaffold

- Architecture overview: `README.md` (section "Architecture at a glance")
- Weekend-by-weekend plan: `DEVELOPMENT.md`
- Test strategy: `TESTING.md`
- Install guide: `PREREQUISITES.md`

## Non-fit list (quick reference)

Arikizu is not the right system for:

1. Low-latency sub-10ms control loops (PLC, motor control, safety stops)
2. Pure cloud workloads with no privacy or edge constraint
3. Pure training workflows (use PyTorch Lightning, Modal, etc.)
4. Single-model single-task use cases (just use the library directly)
5. Non-AI automation (use n8n, Zapier, native scripts)

## Five-point qualification checklist

A workload is a good fit if at least four of the following are true:

- [ ] Multi-modal (vision + audio + docs + reasoning, not one of them)
- [ ] Private by requirement (regulated, air-gapped, or privacy-sensitive)
- [ ] Operated by non-engineers (plant floor, nurses, deck crew)
- [ ] Subject to compliance review (HIPAA, GDPR, DPDP, EU AI Act, etc.)
- [ ] Needs a human in the loop (approval gate, correction, annotation)

## Eleven target verticals

1. Factory floor QA
2. Hospital triage support
3. Maritime engineer-room monitoring
4. Construction site safety
5. Oil rig operations
6. Pharma manufacturing
7. Defense tactical support
8. Heritage preservation
9. Agriculture field ops
10. Utilities field maintenance
11. Research lab assistance
