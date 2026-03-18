import sys
import subprocess
import glob
if sys.version_info < (3, 0):
    import commands  # noqa: F401 used in _getRevision* Python 2 branches
import datetime
import os
import time
import shutil
import pathlib
import re
import hashlib
import json

from OpalRegressionTests.reporter import Reporter
from OpalRegressionTests.reporter import TempXMLElement
import OpalRegressionTests.stattest as stattest
from OpalRegressionTests.sitegen import write_report_assets, write_run_report, update_overview

class OpalRegressionTests:
    def __init__(self, base_dir, tests, opalx_args, publish_dir=None, timestamp=None, plots_dir=None, logs_dir=None, opalx_exe=None):
        self.base_dir = base_dir
        self.tests = tests
        self.opalx_args = opalx_args
        self.publish_dir = publish_dir
        self.plots_dir = plots_dir
        self.logs_dir = logs_dir
        self.opalx_exe = opalx_exe
        self.totalNrPassed = 0
        self.totalNrTests = 0
        self.rundir = sys.path[0]
        self.today = datetime.datetime.today()
        self.timestamp = timestamp

    def run(self):
        rep = Reporter()
        rep.appendReport("Start Regression Test on %s \n" % self.today.isoformat())
        rep.appendReport("==========================================================\n")

        if not self.timestamp:
            self.timestamp = self.today.strftime("%Y-%m-%d")

        self._addDate(rep)
        run_results = {
            "timestamp": self.timestamp,
            "started_at": self.today.isoformat(),
            "opalx_exe": self.opalx_exe,
            "revisions": {},
            "summary": {"total": 0, "passed": 0, "failed": 0, "broken": 0},
            "simulations": [],
        }

        for test in self.tests:
            rt = RegressionTest(self.base_dir, test, self.opalx_args, timestamp=self.timestamp)
            rt.run()
            self.totalNrTests += rt.totalNrTests
            self.totalNrPassed += rt.totalNrPassed
            rt.publish(self.plots_dir, self.logs_dir)
            if rt.result is not None:
                run_results["simulations"].append(rt.result)

        self._addRevisionStrings(rep)
        run_results["revisions"] = {
            "code_full": self._getRevisionOpalx(),
            "tests_full": self._getRevisionTests(),
        }

        # Summary
        # Reporter counts are string-based and include old text; prefer computed state counts from results.
        for sim in run_results["simulations"]:
            for t in sim.get("tests", []):
                run_results["summary"]["total"] += 1
                state = t.get("state")
                if state == "passed":
                    run_results["summary"]["passed"] += 1
                elif state == "failed":
                    run_results["summary"]["failed"] += 1
                elif state == "broken":
                    run_results["summary"]["broken"] += 1

        if self.publish_dir:
            os.makedirs(self.publish_dir, exist_ok=True)
            results_json = os.path.join(self.publish_dir, "results.json")
            with open(results_json, "w", encoding="utf-8") as f:
                json.dump(run_results, f, indent=2, sort_keys=False)

            report_root = os.path.abspath(os.path.join(self.publish_dir, "..", ".."))
            write_report_assets(report_root)
            write_run_report(report_root=report_root, run_dir=self.publish_dir, results=run_results)
            update_overview(report_root=report_root)

        rep.appendReport("\nSummary: {passed} / {total} tests passed \n".format(
            passed = self.totalNrPassed,
            total  = self.totalNrTests))

        rep.appendReport("\n==========================================================\n")
        rep.appendReport("Finished Regression Test on %s \n" %
                         datetime.datetime.today().isoformat())
        print (rep.getReport())

    def _getRevisionTests(self):
        if sys.version_info < (3,0):
            return commands.getoutput("git rev-parse HEAD")
        else:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return (result.stdout or "").strip() if result.returncode == 0 else ""

    def _getRevisionOpalx(self):
        exe = os.path.join(os.getenv("OPALX_EXE_PATH", ""), "opalx")
        if sys.version_info < (3,0):
            src_dir = os.path.abspath(os.path.join(os.path.dirname(exe), "..", "..", "..", "src"))
            return commands.getoutput("cd " + src_dir + " && git rev-parse HEAD")
        else:
            src_dir = os.path.abspath(os.path.join(os.path.dirname(exe), "..", "..", "..", "src"))
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    cwd=src_dir,
                )
            except (OSError, subprocess.SubprocessError):
                return ""

            return (result.stdout or "").strip() if result.returncode == 0 else ""

    def _addDate(self, rep):
        date_report = TempXMLElement("Date")
        startDate_report = TempXMLElement("start")
        startDate_report.appendTextNode (self.today.isoformat())
        date_report.appendChild(startDate_report)
        rep.appendChild(date_report)

    def _addRevisionStrings(self, rep):
        revision_report = TempXMLElement("Revisions")

        revisionCode = self._getRevisionOpalx()
        if not revisionCode:
            sys.stderr.write("WARNING: Could not determine OPALX git revision.\n")
        code_report = TempXMLElement("code")
        code_report.appendTextNode(revisionCode[0:7])
        revision_report.appendChild(code_report)

        full_code_report = TempXMLElement("code_full")
        full_code_report.appendTextNode(revisionCode)
        revision_report.appendChild(full_code_report)

        revisionTests = self._getRevisionTests()
        tests_report = TempXMLElement("tests")
        tests_report.appendTextNode(revisionTests[0:7])
        revision_report.appendChild(tests_report)

        full_tests_report = TempXMLElement("tests_full")
        full_tests_report.appendTextNode(revisionTests)
        revision_report.appendChild(full_tests_report)

        rep.appendChild(revision_report)

    # Legacy XML/XSLT publishing removed in favor of JSON+static HTML.

class RegressionTest:

    def __init__(self, base_dir, simname, args, timestamp=None):
        self.dirname = os.path.join (base_dir, simname)
        self.simname = simname
        self.args = args
        self.timestamp = timestamp or datetime.datetime.today().strftime("%Y-%m-%d_%H-%M")
        self.jobnr = -1
        self.totalNrTests = 0
        self.totalNrPassed = 0
        self.queue = ""
        self.date = datetime.date.today().isoformat()
        self.result = None
        self._staged_data_dir = None
        self._baseline_files = set()

    def _stage_generated_files(self):
        """
        Move generated output files into data/ inside this test directory.

        We move only *newly created* files (compared to the baseline captured
        before the simulation run) to avoid moving static inputs shipped with the test.
        """
        data_dir = os.path.join(self.dirname, "data")
        pathlib.Path(data_dir).mkdir(parents=True, exist_ok=True)

        moved_any = False
        keep_names = {
            self.simname + ".in",
            self.simname + ".rt",
            self.simname + ".local",
            self.simname + ".sge",
            "disabled",
        }

        for p in pathlib.Path(self.dirname).iterdir():
            if not p.is_file():
                continue
            if p.name.startswith("."):
                continue
            if p.name in keep_names:
                continue
            if p.name in self._baseline_files:
                continue

            try:
                shutil.move(str(p), os.path.join(data_dir, p.name))
                moved_any = True
            except Exception:
                # Best-effort staging; don't break the run for staging issues
                continue

        if moved_any:
            self._staged_data_dir = data_dir
            if self.result is not None:
                self.result["data_path"] = data_dir
                self.result["data_url"] = "file://" + data_dir

    def _check_md5sum (self, fname_md5sum):
        """
        Check MD5 sum. File content must be compatible with md5sum(1) output.

        Note: Use this function for small files only!
        """
        with open (fname_md5sum, 'r') as f:
            first_line = f.readline ()
            f.close()

        md5sum, fname = first_line.split()
        ok = md5sum == hashlib.md5(open(fname, 'rb').read()).hexdigest()
        return ok


    def _validateReferenceFiles(self):
        """
        This method checks if all files in the reference directory are present
        and if their md5 checksums still concure with the ones stored after
        the simulation run
        """
        rep = Reporter()
        os.chdir(self.dirname)
        os.chdir("reference")
        allok = True

        for suffix in  [".stat"]:
            fname = self.simname + suffix
            fname_md5 = fname + ".md5"
            if not os.path.isfile(fname):
                rep_string = "\t Reference file %s is missing!\n % (fname)"
                allok = False
            if os.path.islink(fname_md5):
                continue
            if not os.path.isfile(fname_md5):
                rep_string = "\t Reference file %s is missing!\n % (fname_md5)"
                allok = False
                continue
            chksum_ok =  self._reportReferenceFiles(fname_md5)
            allok = allok and chksum_ok

        return allok


    def _validateOutputFiles(self):
        """
        This method checks if all output files needed to compare with
        reference files files in the reference directory are present
        """
        rep = Reporter()
        allok = True

        for suffix in ['.stat']:
            outFiles = [x for x in os.listdir(".") if x.endswith(suffix)]
            refFiles = [x for x in os.listdir("reference") if x.endswith(suffix)]
            if bool(refFiles):
                if not bool(outFiles):
                    allok = False
                    rep.appendReport("\t ERROR: Reference output file %s %s \n" % (
                        refFiles, 'FAILED'))

        return allok


    def _reportReferenceFiles (self, fname):
        rep = Reporter()
        chksum_ok = self._check_md5sum(fname)
        rep.appendReport("\t Checksum for reference %s %s \n" % (
            fname, ('OK' if chksum_ok else 'FAILED')))
        return chksum_ok

    def _cleanup(self):
        """
        cleanup all OLD job files if there are any
        """
        for p in pathlib.Path(".").glob(self.simname + "-RT.*"):
            p.unlink()

        for p in pathlib.Path(".").glob(self.simname + "*.png"):
            p.unlink()

        for p in pathlib.Path(".").glob("*.loss"):
            p.unlink()

        for p in pathlib.Path(".").glob("*.smb"):
            p.unlink()

        if os.path.isfile(self.simname + ".stat"):
            os.remove (self.simname + ".stat")

        if os.path.isfile (self.simname + ".lbal"):
            os.remove (self.simname + ".lbal")

        if os.path.isfile (self.simname + ".out"):
            os.remove (self.simname + ".out")

    def run(self, run_local = True, q = None):
        os.chdir(self.dirname)
        self.queue = q
        self._cleanup()
        self._validateReferenceFiles()
        # Capture baseline file set (static inputs shipped with the test)
        self._baseline_files = {p.name for p in pathlib.Path(self.dirname).iterdir() if p.is_file()}

        rep = Reporter()
        rep.appendReport("Run regression test " + self.simname + "\n")
        success = False
        # for the time being run_local is always true!
        if run_local:
            success = self.mpirun()
        else:
            # :FIXME: this is broken!
            self.submitToSGE()
            self.waitUntilCompletion()

        # copy to out file
        if os.path.isfile (self.simname + "-RT.o"):
            shutil.copy (self.simname + "-RT.o", self.simname + ".out")

        output_ok = self._validateOutputFiles()
        if output_ok:
            rep.appendReport("Reference output files OK\n")
        else:
            # Do not abort: still parse the .rt file so we can report
            # each requested check as broken (missing outputs, execution error, etc.).
            rep.appendReport("ERROR: output validation failed; marking checks as broken where applicable\n")

        simulation_report = TempXMLElement("Simulation")
        simulation_report.addAttribute("name", self.simname)
        simulation_report.addAttribute("date", "%s" % self.date)
        self.result = {
            "name": self.simname,
            "date": self.date,
            "description": "",
            "tests": [],
            "log_relpath": None,
        }

        rt_filename = self.simname + ".rt"
        if os.path.exists(rt_filename):
            with open(rt_filename, "r") as infile:
                tests = [line.rstrip('\n') for line in infile]

            description = tests[0].lstrip("\"").rstrip("\"")
            if not success:
                description += ". Test failed."
            simulation_report.addAttribute("description", description)
            self.result["description"] = description

            rep.appendChild(simulation_report)
            # loop over all tests in rt file, first line is a comment, skip this line
            for i, test in enumerate(tests[1::]):
                try:
                    test_root = TempXMLElement("Test")
                    passed = self.checkResult(test, test_root)
                    if passed is not None:
                        self.totalNrTests += 1
                        if passed:
                            self.totalNrPassed += 1
                        simulation_report.appendChild(test_root)

                        # capture structured info (for report)
                        r = getattr(self, "_last_check_result", None)
                        if r is not None:
                            self.result["tests"].append(r)
                except Exception:
                    exc_info = sys.exc_info()
                    sys.excepthook(*exc_info)
                    rep.appendReport(
                        ("Test broken: didn't succeed to parse %s.rt file line %d\n"
                         "%s\n"
                         "Python reports\n"
                         "%s\n\n") % (self.simname, i+2, test, exc_info[1])
                    )
        else:
            # Fallback if .rt file is missing: report based on execution success only
            description = "No definition file (.rt) found"
            if not success:
               description += ". Test failed (execution error or output missing)."
            else:
               description += ". Test execution successful (no result validation)."
            
            simulation_report.addAttribute("description", description)
            rep.appendChild(simulation_report)
            self.result["description"] = description
            
            # Count this as one coarse-grained check
            self.totalNrTests += 1
            if success and output_ok:
                self.totalNrPassed += 1
            else:
                self.result["tests"].append({
                    "type": "execution",
                    "var": "execution",
                    "mode": "run",
                    "eps": "-",
                    "delta": "-",
                    "state": "broken",
                    "plot": None,
                })

    def publish(self, plots_dir, logs_dir):
        # Copy plots into plots_dir/<simname>/
        if plots_dir:
            sim_plots_dir = os.path.join(plots_dir, self.simname)
            pathlib.Path(sim_plots_dir).mkdir(parents=True, exist_ok=True)
            for p in pathlib.Path(".").glob("*.png"):
                shutil.copy(p, sim_plots_dir)

        # Copy the combined stdout/stderr log into logs_dir
        if logs_dir:
            pathlib.Path(logs_dir).mkdir(parents=True, exist_ok=True)
            src = os.path.join(self.dirname, self.simname + "-RT.o")
            if os.path.isfile(src):
                dst = os.path.join(logs_dir, self.simname + ".out")
                shutil.copy(src, dst)
                if self.result is not None:
                    self.result["log_relpath"] = os.path.relpath(dst, os.path.join(logs_dir, ".."))

        # After capture, move generated files into data/<timestamp>/
        self._stage_generated_files()

    def mpirun(self):
        os.chdir(self.dirname)
        rep = Reporter()
        if not os.access (self.simname+".local", os.X_OK):
            rep.appendReport ("Error: "+self.simname+".local file could not be executed\n")

        cmd = [ os.path.join(".", self.simname + ".local") ]
        cmd.extend(self.args)
        with open(self.simname + "-RT.o", "wb") as f:
            try:
                print ("Running test: " + cmd[0])
                sys.stdout.flush ()
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                out, err = proc.communicate(timeout=1200)
                print (out.decode ('utf-8'))
                print (err.decode ('utf-8'))
                f.write (out)
                f.write (err)
            except subprocess.TimeoutExpired:
                msg = "%s timed out!!!" % (cmd)
                print(msg)
                rep.appendReport(msg)
                return False
            except subprocess.CalledProcessError as e:
                msg = "%s exited with code %d" % (cmd, e.returncode)
                print(msg)
                rep.appendReport(msg)
                return False

        return True

    def submitToSGE(self):
        # FIXME: we could create a sge file on the fly if no sge is specified
        # for a give test ("default sge")
        qsub_command = "qsub " + self.queue + " " + self.simname + ".sge"
        qsub_command += "-v REG_TEST_DIR=" + self.dirname + ",OPALX_EXE_PATH=" + os.getenv("OPALX_EXE_PATH")
        submit_out = subprocess.getoutput(qsub_command)
        self.jobnr = str.split(submit_out, " ")[2]

    def waitUntilCompletion(self):
        username = subprocess.getoutput("whoami")
        qstatout = subprocess.getoutput("qstat -u " + username + " | grep \"" + self.jobnr + "\"")
        while len(qstatout) > 0:
            #we only check every 30 seconds if job has finished
            time.sleep(30)
            qstatout = subprocess.getoutput("qstat -u " + username + " | grep \"" + self.jobnr + "\"")

    def checkResult(self, test, root):
        """
        handler for comparison of various output files with reference files

        Note that we do something different for loss tests as the file name in
        general is not <simname>.loss, rather it is <element_name>.loss

        For smb tests the file name is <simname>-bunch-idBunch.smb
        """
        nameparams = str.split(test,"\"")
        var = nameparams[1]
        params = str.split(nameparams[2].lstrip(), " ")
        rtest = 0
        if "stat" in test:
            rtest = stattest.StatTest(var, params[0], float(params[1]),
                                      self.dirname, self.simname)
        else:
            return None

        passed = rtest.checkResult(root)
        self._last_check_result = getattr(rtest, "last_result", None)
        return passed
