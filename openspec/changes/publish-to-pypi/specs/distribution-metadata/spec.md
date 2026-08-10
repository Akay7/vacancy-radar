## ADDED Requirements

### Requirement: Distribution declares complete PyPI landing-page metadata
The `[project]` table in `pyproject.toml` SHALL declare `authors`,
`keywords`, `classifiers`, and a `[project.urls]` table containing at
minimum a `Homepage` (or `Repository`) URL and an `Issues` URL, in
addition to the existing `name`, `version`, `description`, `readme`,
`requires-python`, `license`, and `dependencies` fields.

The `classifiers` list SHALL include a development-status classifier, a
license classifier, an `Intended Audience` classifier, and a
`Programming Language :: Python :: 3.12` classifier.

#### Scenario: Built wheel metadata carries authors, URLs, and classifiers
- **GIVEN** the project is built with `uv build`
- **WHEN** the wheel's `.dist-info/METADATA` file is read
- **THEN** it contains at least one `Author` or `Author-email` field
- **THEN** it contains at least one `Project-URL` field
- **THEN** it contains at least four `Classifier` fields
- **THEN** it contains a `Requires-Python` field whose value admits 3.12

#### Scenario: README is carried as the long description
- **GIVEN** the project is built with `uv build`
- **WHEN** the wheel's `.dist-info/METADATA` file is read
- **THEN** `Description-Content-Type` is set to a Markdown content type
- **THEN** the long-description body is non-empty

### Requirement: License is declared as an SPDX expression and shipped with the distribution
The `[project]` table SHALL declare `license` as the SPDX expression
string `"MIT"` and SHALL declare `license-files` including the
repository's `LICENSE` file. The `[build-system].requires` entry SHALL
pin a `hatchling` floor new enough to emit PEP 639 license metadata.

#### Scenario: LICENSE is included in the built wheel
- **GIVEN** the project is built with `uv build`
- **WHEN** the wheel archive's contents are listed
- **THEN** a `LICENSE` file is present under the `.dist-info/licenses/`
  directory
- **THEN** the wheel's `METADATA` declares the MIT license via a
  `License-Expression` field

#### Scenario: LICENSE is included in the built sdist
- **GIVEN** the project is built with `uv build`
- **WHEN** the sdist archive's contents are listed
- **THEN** a `LICENSE` file is present at the archive root

### Requirement: Both console scripts are declared in the built distribution
The built wheel SHALL declare exactly the two console scripts
`vacancy-radar` (pointing at the CLI app) and `vacancy-radar-mcp`
(pointing at the MCP server entry function), matching
`[project.scripts]` in `pyproject.toml`.

#### Scenario: Wheel entry points list both scripts
- **GIVEN** the project is built with `uv build`
- **WHEN** the wheel's `.dist-info/entry_points.txt` is read
- **THEN** the `console_scripts` group contains a `vacancy-radar` entry
- **THEN** the `console_scripts` group contains a `vacancy-radar-mcp`
  entry

### Requirement: Distribution version has a single source
The version published to PyPI SHALL come from `[project].version` in
`pyproject.toml`, and no other file in the repository SHALL hardcode a
release version string. `vacancy_radar.__version__` SHALL continue to
derive its value from installed distribution metadata rather than a
literal.

#### Scenario: No second version literal exists in the package source
- **GIVEN** the repository source tree
- **WHEN** `src/vacancy_radar/` is searched for an assignment of a
  three-part numeric version literal to `__version__`
- **THEN** the only such literal is the not-installed fallback, and the
  primary value is read from distribution metadata

### Requirement: Packaging metadata is enforced by the test suite
The repository SHALL contain a test that builds the distribution into a
temporary directory and asserts the metadata requirements above, so that
a regression in packaging metadata fails CI rather than degrading a
future release.

#### Scenario: Packaging test runs as part of the normal suite
- **GIVEN** a checkout with `uv` available on PATH
- **WHEN** `pytest` is run
- **THEN** the packaging test builds the distribution and asserts on the
  wheel's entry points, license file, and classifiers
- **THEN** the build is written to a temporary directory, leaving the
  repository's `dist/` directory untouched

#### Scenario: Packaging test skips without the build tool
- **GIVEN** an environment where `uv` is not available on PATH
- **WHEN** `pytest` is run
- **THEN** the packaging test is skipped rather than failed
