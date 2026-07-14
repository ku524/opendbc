# Repository-Local Agent Instructions

## Project Intent

- This repository is a personal custom fork for the owner's Hyundai Sonata LF Hybrid.
- The goal is correct, safe operation on the owner's vehicle and practical deployment.
- This work is not intended for an upstream sunnypilot or commaai merge.
- Do not optimize work for upstream acceptance, generalized maintainership, or review optics.

## Scope And Tests

- Prioritize production changes that directly affect the requested custom behavior, runtime correctness, panda safety, or on-car deployment.
- Add focused tests when they protect behavior or safety logic being changed.
- Do not proactively add test-only hardening, exhaustive negative controls, generalized cross-platform coverage, refactors, provenance machinery, review prompts, or status-document churn solely to satisfy speculative or adversarial review feedback.
- Treat Low or nonblocking test-coverage gaps as report-only unless the user explicitly asks to implement them.
- When production behavior is already correct, do not change tests merely to lock down every hypothetical future regression.
- Before changing shared APIs or unrelated brands, establish that the expansion is required for this custom vehicle to build or run. Report optional cleanup instead of implementing it.

## Review Feedback

- Independently verify every review finding.
- Classify findings as one of:
  1. custom runtime or vehicle-safety defect,
  2. custom deployment blocker,
  3. upstream/general-quality concern.
- Fix categories 1 and 2. Report category 3 without implementation unless the user explicitly requests it.
- Do not convert a nonblocking review suggestion into a deployment blocker without direct evidence for this vehicle.

## Safety Boundary

- The personal-fork scope does not relax safety-critical verification.
- Keep focused validation for panda safety, CAN validity, radar disable and recovery, brake disengagement, gas override, and unintended longitudinal actuation.
- Offline tests do not replace the staged on-car gates documented for this vehicle.

## Git And Pull Requests

- Open pull requests only against `ku524/opendbc` unless the user explicitly names another personal repository.
- Never open or prepare an upstream sunnypilot or commaai pull request by default.
- Keep custom-fork commits and PR descriptions focused on behavior relevant to the owner's vehicle.
