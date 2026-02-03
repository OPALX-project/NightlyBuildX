# NightlyBuildX

Automated build and testing framework for OPALX. This repository contains scripts to fetch, build, and test the OPALX project and its regression tests.

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

### Options

*   `--config=FILE`: Specify a configuration file (e.g., from `scripts/config/`).
*   `--publish-dir=DIR`: Directory to publish HTML results.
*   `--force`, `-f`: Force compilation and running of all tests.
*   `--compile`: Force compilation.
*   `--unit-tests`: Force running unit tests (not implemented yet).
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
  <branch>/
    src/              # OPALX source code (shared across architectures)
    tests/            # Regression tests (shared across architectures)
    <architecture>/
      build/          # Build directory (architecture-specific)
```

This structure allows:
- **Shared source code** across architectures (efficient, no duplication)
- **Separate build directories** per architecture (isolated builds)
- **Shared test repository** (tests are the same, only execution differs)

## Configuration

Configuration files in `scripts/config/` allow you to customize:
*   Git branches for source and tests.
*   CMake arguments (e.g., Build type, Platforms).
*   OPALX arguments.
*   **Architecture**: Define the build architecture (e.g., `cpu-serial`, `cpu-openmp`, `gpu-cuda-a100`). This organizes builds and test results by architecture, allowing multiple configurations to run independently.

### Example Configuration

```bash
# scripts/config/debug-cpu.conf
architecture="cpu-serial"
branch="master"
cmake_args+=("-DBUILD_TYPE=Debug")
cmake_args+=("-DPLATFORMS=SERIAL")
```

The architecture setting affects:
*   Build directory layout: `workspace/<branch>/<architecture>/build/`
*   Published results structure: `<publish-dir>/<test-type>/<branch>/<architecture>/`
*   HTML report titles to clearly identify which architecture was tested

**Note**: Source code and tests are shared across architectures to avoid duplication, while build directories are architecture-specific to allow parallel builds.

