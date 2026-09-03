# Public release checklist

- [ ] `python -m pytest -q` passes without Abaqus; the real-Abaqus test is skipped or explicitly enabled.
- [ ] `python -m build` produces an sdist and wheel.
- [ ] The synthetic multimodal validate/build/export/inspect flow completes.
- [ ] Tracked files contain no raw experiments, ODB/CAE files, checkpoints, credentials, private manifests, or machine-specific paths.
- [ ] All public fixtures are synthetic or confirmed redistributable.
- [ ] No unlicensed UMAT/VUMAT or private material card is present.
- [ ] Git author identity is configured by the human contributor.
- [ ] The user has confirmed the remote destination and public/private visibility before any repository creation or push.
