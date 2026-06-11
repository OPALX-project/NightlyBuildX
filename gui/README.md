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
- Builds and shows the exact `scripts/run_tests` command before running it.
- Streams run output in the browser.
- Links published result pages from `/Users/adelmann/opalx-html`.

The GUI is a thin wrapper around the existing `scripts/run_tests` workflow. The runner uses one OPALX checkout at `workspace/opalx`, one regression-test checkout at `workspace/regression-tests-x`, and a reused build tree at `workspace/build/<architecture>`.
