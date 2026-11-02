---
name: Feature request
about: Suggest a change in behavior or a new capability.
title: '[feature] '
labels: ['enhancement', 'triage']
---

**What you're trying to do**

The real-world task, not the solution.

**What's missing**

Which worker, crate, or doc. If this needs a new capability, name it:
`<worker>.<op>`.

**Why Arikizu is the right place for it**

Would a plain shell script, a cron job, or a vanilla Python package not
work? If so, say why.

**Non-fit check**

Against `docs/ARCHITECTURE.md`:

- [ ] Multi-modal (vision + audio + docs + reasoning, not one of them)
- [ ] Private by requirement (regulated, air-gapped, or privacy-sensitive)
- [ ] Operated by non-engineers (plant floor, nurses, deck crew)
- [ ] Subject to compliance review (HIPAA, GDPR, DPDP, EU AI Act, etc.)
- [ ] Needs a human in the loop (approval gate, correction, annotation)

Four or more boxes checked means it probably belongs in Arikizu. Fewer
is fine; just explain the fit.
