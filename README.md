# NightlyBuildX

Automated build and testing framework for OPALX. This repository contains scripts to fetch, build, and test the OPALX project and its regression tests.

NightlyBuildX now supports a local regression-analysis workflow in addition to the full nightly path. The new **--run-local-now** mode compares existing outputs without updating repositories, rebuilding OPALX, rerunning tests, or launching new
  simulations. The related **--only-generate-web-page** mode can be used from either a single test directory or the parent RegressionTests directory and generates the usual regression HTML/XML report locally, including copied plot assets and index pages.

  Regression comparison plotting now supports two backends. By default the suite uses gnuplot; with --no-gpl it switches to a Python/matplotlib backend. The wrapper checks these dependencies early and fails with a clear message if the required plotting
  tool is not available. The Python plots were also cleaned up for readability, including explicit scientific tick labels and improved delta-axis formatting.

  The reporting side was extended as well. Local runs can generate plot-summary.html, and published regression pages now include per-test timing-overview plots when both timing.dat and reference/timing.dat are available. The results pages also show a
  global run-metadata block with host, architecture, backend, ranks, threads, and device. Finally, **run_tests* now accepts **--opalx-branch** and **--regtests-branch** so branch selection can be overridden directly on the command line while still allowing config
  files to provide the defaults.



## Overview

The core of this system is the `scripts/run_tests` bash script:
1.  **Setup**: Creates a workspace directory structure.
2.  **Fetch**: Clones or updates the OPALX source code and regression tests repositories.
3.  **Build**: Compiles OPALX.
4.  **Test**: Runs regression tests.
5.  **Report**: Generates HTML reports organized by architecture:
    - **Master landing page**: Single overview showing all architectures at `overview/<branch>/index.html`
    - **Architecture-specific pages**: Detailed history per configuration
    - **Test results**: Individual test outputs and comparisons

## Usage

To run the standard workflow (update, build if needed, test if needed):

```bash
./scripts/run_tests
```

## OPALX Lab GUI

NightlyBuildX also includes a local browser GUI for day-to-day regression-test work:

```bash
python3 -B gui/opalx_gui.py
```

By default it starts a local web server and prints the URL to open in a browser. If the default port is already used, choose another one:

```bash
OPALX_GUI_PORT=8769 python3 -B gui/opalx_gui.py
```

### GUI Prerequisites

Before using OPALX Lab, prepare these local paths:

*   **NightlyBuildX checkout**: Run the GUI from this repository.
*   **OPALX source checkout**: Keep at least one local OPALX source checkout, typically `~/git/opalx`.
*   **OPALX build directory**: For reusing an existing executable, the build directory must contain `src/opalx`, for example `~/git/opalx/build/src/opalx`.
*   **Regression tests checkout**: The GUI uses `workspace/regression-tests-x` for Run Builder tests. If it does not exist, `scripts/run_tests` can create/update it during a run.
*   **Publish directory**: Results are written to the selected publish directory, defaulting to `~/opalx-html`.
*   **Python plotting**: The default GUI command enables Python plots (`--no-gpl`), so `matplotlib` must be importable by `python3`.
*   **Unit tests**: To run unit tests from an existing build, the OPALX build must have unit tests enabled and be usable with `ctest`.

The **Run Builder** source selector can point either to an OPALX source directory or to an existing OPALX build directory. If a source directory has a matching local build, OPALX Lab reuses that build when `Compile` is unchecked. If `Compile` is checked, the managed workspace checkout/build is used.

The **Reference Builder** uses the executable selected in Run Builder. Its regression-test source field can be edited; paths under the home directory are shown as `~`, and both `~` and `$HOME` are accepted as input.

Runtime GUI state is stored in:

```text
gui/ui-state.json
gui/run-history.json
```

Delete `gui/run-history.json` for a clean Results Browser history. Published XML/HTML/plots under `~/opalx-html` are not removed.

### Options

*   `--config=FILE`: Specify a configuration file (e.g., from `scripts/config/`).
*   `--publish-dir=DIR`: Directory to publish HTML results.
*   `--force`, `-f`: Force compilation and running of all tests.
*   `--compile`: Force compilation.
*   `--unit-tests`: Force running unit tests (runs `ctest -L unit` in the build directory; requires `OPALX_ENABLE_UNIT_TESTS=ON` in your config).
*   `--reg-tests`: Force running regression tests.

### Example

Run with a specific configuration (e.g., Debug CPU):

```bash
bash NightlyBuildX/scripts/run_tests \
    --config=NightlyBuildX/scripts/config/debug-cpu.conf \
    --publish-dir=regtest-results
```

## Directory Structure

The script creates a `workspace` directory (ignored by git) where all work happens:

```
workspace/
  opalx/              # Single OPALX checkout; branches are selected with git checkout
  regression-tests-x/ # Single regression-tests checkout
  build/
    <architecture>/   # Reused build directory for the selected OPALX branch/config
```

This structure allows:
- **One OPALX clone** reused by checking out branches instead of cloning per branch
- **One regression test clone** reused by checking out the selected tests branch
- **Stable build directories** per architecture/config family

## Configuration

Configuration files in `scripts/config/` allow you to customize:
*   Git branches for source and tests.
*   CMake arguments (e.g., Build type, Platforms).
*   OPALX arguments.
*   **Architecture**: Define the build architecture (e.g., `cpu-serial`, `cpu-openmp`, `gpu-cuda-a100`). This organizes builds and test results by architecture, allowing multiple configurations to run independently.
*   **Unit tests**: Set `do_unittests='yes'` in the config to run unit tests (`ctest -L unit`) after each build when using that config; set to `'no'` to disable. The provided configs enable unit tests by default.

### Example Configuration

```bash
# scripts/config/debug-cpu.conf
architecture="cpu-serial"
branch="master"
cmake_args+=("-DBUILD_TYPE=Debug")
cmake_args+=("-DPLATFORMS=SERIAL")
```

The architecture setting affects:
*   Build directory layout: `workspace/build/<architecture>/`
*   Published results structure: `<publish-dir>/<test-type>/<branch>/<architecture>/`
*   HTML report titles to clearly identify which architecture was tested

**Note**: Source code and tests use one shared checkout each. Switching branches happens with `git checkout`, and build directories are reused by architecture.

## Regression Tests
The regression tests are located on the `cleanup` branch in the [regression-tests-x](https://github.com/OPALX-project/regression-tests-x/tree/cleanup) repository of the OPALX project.
