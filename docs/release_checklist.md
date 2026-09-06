# Public release checklist

This checklist applies to the complete upload candidate, including tracked files,
non-ignored new files, build contents and reachable Git history. A previous test
count or scan does not certify later changes. Use the final dated verification
report to record the source version, commands, outputs and artifact checks.

The first formal release is `v0.1.0`. Its current evidence is recorded in
[the release verification](verification/2026-09-06-v0.1.0-release.md).

## Technical gates

- [ ] The final `python -m pytest -q` run passes without requiring Abaqus. Optional
  installed-wheel and real-Abaqus tests are clearly skipped or explicitly enabled.
- [ ] `python -m build` produces both sdist and wheel, and installing the wheel
  outside the source checkout finds the default policy and ODB extraction script.
- [ ] The synthetic multimodal validate/build/HDF5/NPZ/inspect flow completes in
  a new run directory. HDF5 round-trip preserves the declared arrays and metadata.
- [ ] PyG export is tested with the optional dependencies and explicit graph
  contract, or its skip is reported as an unverified optional capability.
- [ ] Data-validation failures and incomplete/changed extraction evidence block
  formal export. Valid solver-incomplete experimental samples remain exportable.
- [ ] Native INCLUDE dependencies are bound, confined, staged and checked through
  the CLI. Staging alone does not bypass semantic solver readiness.
- [ ] A small real-solver check, when available and authorized, records separate
  datacheck, compile/link and analysis evidence, then ODB extraction and export.
  Missing data/environment produces explicit blocked evidence. Offline fake
  solver results are never counted as this check.
- [ ] The final audit findings are either fixed with verified regression coverage
  or explicitly outside the documented initial-release scope.

## Public-file gates

- [ ] Review `git ls-files --cached --others --exclude-standard`, including
  `docs/superpowers/` and new verification documents, before staging files.
- [ ] Candidates and build archives contain no raw experiments, ODB/CAE files,
  checkpoints, private material cards, private manifests, credentials or
  developer-machine installation paths.
- [ ] Reachable history has been separately reviewed for the same categories.
  Any historical findings have an explicit disposition; cleaning a current
  document must not be reported as removing that content from old commits.
- [ ] Review credential and path pattern hits by filename/category. Do not print
  suspected secret values in reports. Generic format mentions and synthetic
  rejection tests are reviewed in context rather than silently excluded.
- [ ] Public fixtures are small synthetic inputs or have confirmed redistribution
  terms. Public-source URL/hash manifests do not include the downloaded files.
- [ ] No UMAT/VUMAT of unconfirmed origin/license is in the upload candidate.
- [ ] Documentation distinguishes semantic parsing from native asset registration,
  implemented solver profiles from extension points, and toolchain checks from
  scientific CPFE validation.

## Publication actions

- [ ] Verify the repository's configured author identity; do not invent a name or
  email if missing.
- [ ] Verify the existing remote and visibility match the user's already
  authorized destination. Do not create a duplicate repository or force-push.
- [ ] Stage only the reviewed candidate, inspect the staged diff, commit and push
  only after the required technical/public-file gates pass.
- [ ] Verify remote CI on the uploaded commit and report the commit and run link.
- [ ] Include Apache-2.0 `LICENSE`, project `NOTICE`, third-party attribution and
  SPDX package metadata, using the scope recorded in [licensing.md](licensing.md).
- [ ] Check package metadata with `python -m twine check --strict <dist-files>`.
- [ ] Publish a new annotated version tag and GitHub Release after both CI jobs
  pass, attaching the verified wheel and sdist and version-specific install links.
- [ ] Download the published attachments and verify their contents and installation.

The owner authorized license selection and the first GitHub release. Apache-2.0
applies to project code; the listed public tensile case materials use CC-BY-4.0.
PyPI publication is a separate follow-up.
