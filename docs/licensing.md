# License review for v0.1.0

The owner authorized license selection and the first formal GitHub release.
Project code, documentation and synthetic fixtures use **Apache-2.0**, with
the public tensile materials listed in
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) under **CC-BY-4.0**.

Apache-2.0 permits reuse, modification and redistribution, including commercial
use, and provides an explicit contributor patent grant. This supports reuse
of the pipeline in research and engineering software. Its attribution and
redistribution conditions are set out in the [license text](../LICENSE).
The decision follows the current ownership and dependency review.

## Source and dependency review

The four commits preceding this release have the repository's configured
author, `17636365690`. The reviewed source tree contains project implementations,
tests, small synthetic inputs and source references. No separately licensed
third-party source implementation was identified in the release candidate.

The installed direct dependency metadata was reviewed on 2026-09-06:

| Use | Packages | Upstream license metadata |
|---|---|---|
| Core | h5py 3.16.0, pandas 3.0.5 | BSD-3-Clause / BSD |
| Core | NumPy 2.5.2 | BSD-3-Clause, 0BSD, MIT, Zlib, CC0-1.0 |
| Core | pydantic 2.13.5, PyYAML 6.0.3 | MIT |
| Native/training | SciPy 1.18.1, openpyxl 3.1.5 | BSD / MIT |
| Training/graph | torch 2.8.0+cpu, torch-geometric 2.7.0 | BSD-3-Clause / MIT |
| Example plotting | matplotlib 3.11.1 | Matplotlib license, PSF-based |
| Development/build | pytest 9.1.1, build 1.6.0, setuptools 78.1.0 | MIT |
| Release metadata check | twine 7.0.0 | Apache-2.0 |

These are review-environment versions, rather than a dependency lock. Pip
installs dependencies as separate distributions carrying their own notices;
they are not incorporated into the project's Apache-2.0 grant. The archive
review checks the actual package contents for bundled source or binaries.

## Public experimental materials

The [Zenodo source record](https://zenodo.org/records/10820299) confirms
KupferDigital version 2, its seven creators and CC-BY-4.0. The third-party
notice provides full attribution, links and the changes made to the data.
The project's processed figures, result summary and reference INP use
CC-BY-4.0 as listed there; the preparation and training scripts use Apache-2.0.
The original archive and raw experimental files remain in local source storage.

The NTNU manifest remains an external MIT-licensed source reference. Other
datasets mentioned in verification reports are local-read evidence; their
source files are supplied separately.

## Distribution metadata

The Python wheel and sdist declare `License-Expression: Apache-2.0` and ship
`LICENSE`, `NOTICE` and `THIRD_PARTY_NOTICES.md`. The case files listed under
CC-BY-4.0 are distributed through the GitHub source tree and its source archives.
Versioned README links lead package users to those materials and their terms.

Earlier audit reports describe the license as pending at the time of those
audits. This review records the completed selection for v0.1.0.

References: [Apache licensing FAQ](https://www.apache.org/foundation/license-faq),
[Apache-2.0 terms](https://www.apache.org/licenses/LICENSE-2.0),
[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/),
[setuptools license metadata](https://setuptools.pypa.io/en/stable/userguide/license_migration.html).
