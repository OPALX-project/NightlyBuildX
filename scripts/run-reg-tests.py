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
def scan_for_tests(dir):
    current_dir = os.getcwd()
    os.chdir(dir)
    try:
        tests = set()
        with os.scandir('.') as it:
            for entry in it:
                if entry.name.startswith('.') or not entry.is_dir():
                    continue

                test = entry.name
                basename = os.path.join(test, test)
                if not (
                    os.path.isfile(basename + ".in")
                    and os.path.isdir(os.path.join(test, "reference"))
                    and os.path.isfile(os.path.join(test, "reference", test + ".stat"))
                ):
                    continue

                if os.path.isfile(os.path.join(test, "disabled")):
                    continue

                tests.add(test)
    finally:
        os.chdir(current_dir)

    return sorted(tests)


def resolve_local_scope():
    current_dir = os.getcwd()
    simname = os.path.basename(current_dir)
    basename = os.path.join(current_dir, simname)

    if not (
        os.path.isfile(basename + ".in")
        and os.path.isdir(os.path.join(current_dir, "reference"))
        and os.path.isfile(os.path.join(current_dir, "reference", simname + ".stat"))
    ):
        tests = scan_for_tests(current_dir)
        if not tests:
            print(f"{current_dir} - current directory is neither a regression test directory nor a regression test base directory!")
            sys.exit(1)
        return current_dir, tests

    return os.path.dirname(current_dir), [simname]


def resolve_local_publish_dir():
    return os.getcwd()

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
    parser.add_argument('--run-local-now',
                        dest='run_local_now', action='store_true',
                        help='Only compare existing local outputs and generate plots in the current test directory')
    parser.add_argument('--no-gpl',
                        dest='no_gpl', action='store_true',
                        help='Use Python plotting instead of gnuplot for comparison plots')
    parser.add_argument('--only-generate-web-page',
                        dest='generate_web_page', action='store_true',
                        help='Write a local plot-summary.html page and generate the standard regression results HTML/XML page')

    args = parser.parse_args()

    args.opalx_args = [item for sublist in args.opalx_args for item in sublist]
    #print(args.opalx_args)

    if args.run_local_now:
        base_dir, tests = resolve_local_scope()
    elif args.base_dir:
        base_dir = os.path.abspath(args.base_dir)
        tests = None
    else:
        base_dir = os.getcwd()
        tests = None
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
    elif args.run_local_now and args.generate_web_page:
        publish_dir = resolve_local_publish_dir()
    if publish_dir and not os.path.exists(publish_dir):
        os.makedirs(publish_dir)

    if not args.run_local_now:
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
    if tests is None:
        tests = scan_for_tests(base_dir)
    if args.tests and not args.run_local_now:
        for test in args.tests:
            if not test in tests:
                print("%s - unknown test!" % (test))
                sys.exit(1)
        tests = sorted(args.tests)

    if args.run_local_now:
        print ("Comparing the following local regression test:")
    else:
        print ("Running the following regression tests:")
    for test in tests:
        print ("    {}".format(test))
    
    rt = OpalRegressionTests.OpalRegressionTests(
        base_dir,
        tests,
        args.opalx_args,
        publish_dir,
        args.timestamp,
        use_gnuplot=not args.no_gpl,
        generate_web_page=args.generate_web_page,
    )
    rt.run(compare_only=args.run_local_now)


if __name__ == "__main__":
    main(sys.argv[1:])
