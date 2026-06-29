# OPALX Lab GUI

Local web GUI for working with the shared OPALX checkout, builds, and regression tests.

## Start

```bash
cd /Users/adelmann/git/NightlyBuildX
python3 -B gui/opalx_gui.py
```

Open:

```text
http://127.0.0.1:8765
```

## What It Does

- Lists OPALX branches from `workspace/opalx` and its remote branch list.
- Lists configs from `scripts/config/*.conf`.
- Lists regression tests from `workspace/regression-tests-x/RegressionTests`.
- Lets the user select the OPALX branch for the run.
- Lets the user select the regression-tests-x branch used for tests and references.
- Supports compile/run/publish workflows through the existing `scripts/run_tests` command line.
- Builds and shows the exact `scripts/run_tests` command before running it.
- Streams run output in the browser.
- Links published result pages from `/Users/adelmann/opalx-html`.

The GUI is a thin wrapper around the existing `scripts/run_tests` workflow. The runner uses one OPALX checkout at `workspace/opalx`, one regression-test checkout at `workspace/regression-tests-x`, and a reused build tree at `workspace/build/<architecture>`.

The local GUI is for configuring and launching local work. The published result GUI under `opal-live-doc` is separate and read-only: it only browses data from already completed runs.

## Published Output

Local results are written below the selected publish directory, normally `/Users/adelmann/opalx-html`. The generated result pages use the same layout as the published nightly pages:

- `overview/index.html` lists available branches.
- `overview/<branch>/index.html` lists available architectures for a branch.
- `overview/<branch>/<architecture>/index.html` lists available result dates.
- `regressionTests/<branch>/<architecture>/results_<date>_<time>.html` shows a single run.

On result pages, the plot slider selects one plot to display. It does not scroll the result table; wide tables use normal horizontal scrolling.

## Render Existing Results

To refresh HTML from already available published data without compiling or running tests:

```bash
./scripts/run_tests --doNotCompileRun --publish-dir /Users/adelmann/opalx-html
```

This preserves existing branch, architecture, result, and plot asset names.
