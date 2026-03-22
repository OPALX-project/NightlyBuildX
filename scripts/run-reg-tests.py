#!/usr/bin/env python3

import sys
import os
import shutil
import argparse

import OpalRegressionTests

"""
Scan given directory for regression tests. Regression tests are stored
in sub-directories whereby the name the directory has the same name as
the regression test.

Regression tests must follow the following directory-layouts:

    DIR Structure:
    name/name.in
         reference/name.stat

"""
def scan_for_tests (dir):
    # Switch to the directory containing regression tests
    os.chdir (dir)

    tests = set ()
    # Iterate through all entries in the directory
    with os.scandir ('.') as it:
        for entry in it:
            # Skip hidden directories (starting with .) or entries that are not directories
            if entry.name.startswith('.') or not entry.is_dir():
                continue

            # check if all files required are available
            test = entry.name
            basename = os.path.join (test, test)

            # A valid test requires:
            # 1. An input file (<name>.in)
            # 3. A 'reference' subdirectory
            if not (os.path.isfile(basename + ".in") and
                    os.path.isdir(os.path.join (test, "reference")) and
                    os.path.isfile(os.path.join (test, "reference", test + ".stat"))):
                continue

            # Check if a 'disabled' file exists to skip this test
            if os.path.isfile(os.path.join(test, "disabled")):
                continue
                
            tests.add (test)
            
    # Return the list of tests sorted alphabetically
    return sorted(tests)

def main(argv):
    parser = argparse.ArgumentParser(description='Run regression tests.')
    parser.add_argument('tests',
                        metavar='tests', type=str, nargs='*', default='',
                        help='regression tests to run (default: all)')
    parser.add_argument('--base-dir',
                        dest='base_dir', type=str,
                        help='base directory with regression tests')
    parser.add_argument('--publish-dir',
                        dest='publish_dir', type=str,
                        help='publish directory')
    parser.add_argument('--plots-dir',
                        dest='plots_dir', type=str,
                        help='directory where plots will be written/copied')
    parser.add_argument('--logs-dir',
                        dest='logs_dir', type=str,
                        help='directory where per-test logs will be written')
    parser.add_argument('--build-dir',
                        dest='build_dir', type=str,
                        help='OPALX build directory (used to read CMakeCache.txt)')
    parser.add_argument('--opalx-exe',
                        dest='opalx_exe', type=str,
                        help='full path to OPALX executable')
    parser.add_argument('--opalx-args',
                        dest='opalx_args', nargs='*', action='append',
                        help='arguments passed to OPAL',
			default=[])
    parser.add_argument('--timestamp',
                        dest='timestamp', type=str,
                        help='timestamp to use in file names',
			default=[])
    parser.add_argument('--unit-tests-summary',
                        dest='unit_tests_summary', type=str,
                        help='path to JSON summary for unit tests',
                        default=None)

    # Support passing tests after a literal "--" (run_tests uses this)
    if "--" in argv:
        idx = argv.index("--")
        known, rest = argv[:idx], argv[idx+1:]
        args = parser.parse_args(known)
        if rest:
            args.tests = rest
    else:
        args = parser.parse_args(argv)

    args.opalx_args = [item for sublist in args.opalx_args for item in sublist]
    #print(args.opalx_args)

    # Get the directory holding the regression tests 
    if args.base_dir:
        base_dir = os.path.abspath(args.base_dir)
    else:
        base_dir = os.getcwd()
    if not os.path.isdir (base_dir):
        print ("%s - regression tests base directory does not exist!" %
               (base_dir))
        sys.exit(1)

    # Directory for publishing results of the regression tests
    publish_dir = None
    if args.publish_dir:
        publish_dir = os.path.abspath(args.publish_dir)
    elif os.getenv("REGTEST_WWW"):
        publish_dir = os.getenv("REGTEST_WWW")
    if publish_dir and not os.path.exists(publish_dir):
        os.makedirs(publish_dir)

    # Resolve OPALX executable
    if args.opalx_exe:
        opalx = os.path.abspath(args.opalx_exe)
    else:
        # fallback to PATH
        opalx = shutil.which("opalx")
        if opalx:
            opalx = os.path.abspath(opalx)

    if not opalx or not (os.path.isfile(opalx) and os.access(opalx, os.X_OK)):
        print("opalx - not found or not executable. Provide --opalx-exe.")
        sys.exit(1)

    os.environ['OPALX_EXE_PATH'] = os.path.dirname(opalx)

    # Scan for the tests
    tests = scan_for_tests(base_dir)
    if args.tests:
        for test in args.tests:
            if not test in tests:
                print("%s - unknown test!" % (test))
                sys.exit(1)
        tests = sorted(args.tests)

    print ("Running the following regression tests:")
    for test in tests:
        print ("    {}".format(test))
    
    plots_dir = os.path.abspath(args.plots_dir) if args.plots_dir else None
    logs_dir = os.path.abspath(args.logs_dir) if args.logs_dir else None
    build_dir = os.path.abspath(args.build_dir) if args.build_dir else None
    unit_tests_summary = os.path.abspath(args.unit_tests_summary) if args.unit_tests_summary else None

    rt = OpalRegressionTests.OpalRegressionTests(
        base_dir=base_dir,
        tests=tests,
        opalx_args=args.opalx_args,
        publish_dir=publish_dir,
        timestamp=args.timestamp,
        plots_dir=plots_dir,
        logs_dir=logs_dir,
        opalx_exe=opalx,
        build_dir=build_dir,
        unit_tests_summary=unit_tests_summary,
    )
    rt.run()


if __name__ == "__main__":
    main(sys.argv[1:])