# NightlyBuildX
Run regression test and unit tests for the OPALX (https://github.com/OPALX-project/OPALX) code.

## Usage
```
bash NightlyBuildX/scripts/run_tests --build <path-to-build> --tests <path-to-reg-tests> --unittests <on/off>
```
- `--build` specifies the build folder, can be `CPU` or `GPU`
- `--tests` specifies the path to the regression tests
- `--unittests` switches unit tests on (default) and off

## Regression Tests
Any folder follwing the structure of https://github.com/rammann/regression-tests-x will work.

```
regression-tests-x/
└── RegressionTests/
    └─ Fodo-long/
        └── Fodo-long.in  
        └── Fodo-long.local  
        └── Fodo-long.rt 
        └── reference/
            └── Fodo-long.out
            └── Fodo-long.stat
    
```
- `*.in` is the input file
- `*.local` contains the run command
- `*.rt` contains the tracked stats and thresholds
- `reference/*.out` contains the reference output file
- `reference/*.stat` contains the reference stat file


## Output
This will generate a `NightlyBuildX/report/index.html` file which can be opened
and contains an overview of all the tests.