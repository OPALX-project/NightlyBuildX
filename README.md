# NightlyBuildX

Automated build and testing framework for OPALX. This repository contains scripts to fetch, build, and test the OPALX project and its regression tests.

## Overview

The core of this system is the `scripts/run_tests` bash script:
1.  **Setup**: Creates a workspace directory structure.
2.  **Fetch**: Clones or updates the OPALX source code and regression tests repositories.
3.  **Build**: Compiles OPALX.
4.  **Test**: Runs regression tests.
5.  **Report**: Optionally publishes HTML reports of the test results.

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
    src/          # OPALX source code
    build/        # Build directory
    tests/        # Regression tests
```

## Configuration

Configuration files in `scripts/config/` allow you to customize:
*   Git branches for source and tests.
*   CMake arguments (e.g., Build type, Platforms).
*   OPALX arguments.

## Regression Tests
The regression tests are located on the `cleanup` branch in the [regression-tests-x](https://github.com/OPALX-project/regression-tests-x/tree/cleanup) repository of the OPALX project.
