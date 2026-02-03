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
                        metavar='tests', type=str, nargs='*', default = '',
                        help='a regression test to run')
    parser.add_argument('--base-dir',
                        dest='base_dir', type=str,
                        help='base directory with regression tests')
    parser.add_argument('--publish-dir',
                        dest='publish_dir', type=str,
                        help='publish directory')
    parser.add_argument('--opalx-exe-path',
                        dest='opalx_exe_path', type=str,
                        help='directory where OPAL binary is stored')
    parser.add_argument('--opalx-args',
                        dest='opalx_args', nargs='*', action='append',
                        help='arguments passed to OPAL',
			default=[])
    parser.add_argument('--timestamp',
                        dest='timestamp', type=str,
                        help='timestamp to use in file names',
			default=[])

    args = parser.parse_args()

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

    # Get the directory holding the OPALX executable
    try:
        if args.opalx_exe_path:
            os.environ['OPALX_EXE_PATH'] = args.opalx_exe_path
        elif os.getenv("OPALX_EXE_PATH"):
            args.opalx_exe_path = os.getenv("OPALX_EXE_PATH")
        else:
            args.opalx_exe_path = os.path.dirname(shutil.which("opalx"))
            os.environ['OPALX_EXE_PATH'] = args.opalx_exe_path

        opalx = os.path.join(args.opalx_exe_path, "opalx")
        if not (os.path.isfile(opalx) and os.access(opalx, os.X_OK)):
            raise FileNotFoundError
    except:
        print ("opalx - not found or not an executablet!")
        sys.exit(1)

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
    
    rt = OpalRegressionTests.OpalRegressionTests(base_dir, tests, args.opalx_args, publish_dir, args.timestamp)
    rt.run()


if __name__ == "__main__":
    main(sys.argv[1:])