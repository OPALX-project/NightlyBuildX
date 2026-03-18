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

from OpalRegressionTests.reporter import Reporter
from OpalRegressionTests.reporter import TempXMLElement
import OpalRegressionTests.stattest as stattest

class OpalRegressionTests:
    def __init__(
        self,
        base_dir,
        tests,
        opalx_args,
        publish_dir = None,
        timestamp = None,
        use_gnuplot = True,
        generate_web_page = False,
    ):
        self.base_dir = base_dir
        self.tests = tests
        self.opalx_args = opalx_args
        self.publish_dir = publish_dir
        self.use_gnuplot = use_gnuplot
        self.generate_web_page = generate_web_page
        self.totalNrPassed = 0
        self.totalNrTests = 0
        self.rundir = sys.path[0]
        self.today = datetime.datetime.today()
        self.timestamp = timestamp

    def run(self, compare_only = False):
        rep = Reporter()
        rep.appendReport("Start Regression Test on %s \n" % self.today.isoformat())
        rep.appendReport("==========================================================\n")

        if not self.timestamp:
            self.timestamp = self.today.strftime("%Y-%m-%d")

        # clean old results if exist
        plot_dir = None
        if self.publish_dir:
            plot_dir = os.path.join(self.publish_dir, "plots_" + self.timestamp)
            if os.path.isdir(plot_dir):
                shutil.rmtree(plot_dir)

        self._addDate(rep)
        for test in self.tests:
            rt = RegressionTest(
                self.base_dir,
                test,
                self.opalx_args,
                self.use_gnuplot,
                generate_web_page=self.generate_web_page,
            )
            if compare_only:
                rt.compare_only()
            else:
                rt.run()
            self.totalNrTests += rt.totalNrTests
            self.totalNrPassed += rt.totalNrPassed
            rt.publish(plot_dir)

        self._addRevisionStrings(rep)

        if self.publish_dir:
            results_file = os.path.join(self.publish_dir, "results_" + self.timestamp + ".xml")
            if os.path.isfile(results_file):
                os.remove (results_file)
            rep.dumpXML(results_file, "plots_" + self.timestamp)
            self._publish_results()

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

    def _publish_results (self):
        rep = Reporter ()

        #webfilename = "results_" + self.timestamp + ".xml"
        webfilename = "results_" + self.timestamp + ".html"

        index_fname = os.path.join (self.publish_dir, "index.html")
        if not os.path.exists(index_fname):
            shutil.copy (os.path.join (self.rundir, os.path.join("html", "index.html")), index_fname)

        # update 'index.html'
        indexhtml = open(index_fname).readlines()

        # search for the string 'insert here'
        for line in range(len(indexhtml)):
            if "insert here" in indexhtml[line]:
                m = re.search(webfilename, indexhtml[line + 1])
                fmt="<a href=\"%s\">%04d-%02d-%02d %02d:%02d</a> [passed:%d | broken:%d | failed:%d | total:%d] <br/>\n"
                text = fmt % (webfilename,
                              self.today.year, self.today.month, self.today.day,
                              self.today.hour, self.today.minute,
                              self.totalNrPassed, rep.NrBroken(), rep.NrFailed(),
                              self.totalNrTests)

                if m != None:
                    # result for today already exist, replace it
                    indexhtml[line+1] = text
                else:
                    # first run
                    indexhtml.insert(line+1, text)
                break
        # write new 'index.html' back
        indexhtmlout = open(index_fname, "w")
        indexhtmlout.writelines(indexhtml)
        indexhtmlout.close()

        # update various files to publish directory
        shutil.copy (os.path.join (self.rundir, "html", "ok.png"), self.publish_dir);
        shutil.copy (os.path.join (self.rundir, "html", "nok.png"), self.publish_dir);
        shutil.copy (os.path.join (self.rundir, "html", "results.xslt"), self.publish_dir)
        shutil.copy (os.path.join (self.rundir, "html", "accordion.js"), self.publish_dir)

class RegressionTest:

    def __init__(self, base_dir, simname, args, use_gnuplot = True, generate_web_page = False):
        self.dirname = os.path.join (base_dir, simname)
        self.simname = simname
        self.args = args
        self.use_gnuplot = use_gnuplot
        self.generate_web_page = generate_web_page
        self.jobnr = -1
        self.totalNrTests = 0
        self.totalNrPassed = 0
        self.queue = ""
        self.date = datetime.date.today().isoformat()

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
        cwd = os.getcwd()
        os.chdir(self.dirname)
        os.chdir("reference")
        allok = True

        try:
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
        finally:
            os.chdir(cwd)

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

        timing_plot = self._write_timing_overview()
        self._process_results(rep, success, timing_plot)
        if self.generate_web_page:
            self._write_local_plot_summary()

    def compare_only(self):
        os.chdir(self.dirname)
        self._validateReferenceFiles()

        rep = Reporter()
        rep.appendReport("Compare local regression test " + self.simname + "\n")

        success = self._validateOutputFiles()
        timing_plot = self._write_timing_overview()
        self._process_results(rep, success, timing_plot)
        self._write_local_plot_summary()

    def _process_results(self, rep, success, timing_plot = None):
        if success:
            rep.appendReport("Reference output files OK\n")
        else:
            return False

        simulation_report = TempXMLElement("Simulation")
        simulation_report.addAttribute("name", self.simname)
        simulation_report.addAttribute("date", "%s" % self.date)

        rt_filename = self.simname + ".rt"
        if os.path.exists(rt_filename):
            with open(rt_filename, "r") as infile:
                tests = [line.rstrip('\n') for line in infile]

            description = tests[0].lstrip("\"").rstrip("\"")
            if not success:
                description += ". Test failed."
            simulation_report.addAttribute("description", description)

            rep.appendChild(simulation_report)
            for i, test in enumerate(tests[1::]):
                try:
                    test_root = TempXMLElement("Test")
                    passed = self.checkResult(test, test_root)
                    if passed is not None:
                        self.totalNrTests += 1
                        if passed:
                            self.totalNrPassed += 1
                        simulation_report.appendChild(test_root)
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
            description = "No definition file (.rt) found"
            if not success:
               description += ". Test failed (execution error or output missing)."
            else:
               description += ". Test execution successful (no result validation)."

            simulation_report.addAttribute("description", description)
            rep.appendChild(simulation_report)

            self.totalNrTests += 1
            if success:
                self.totalNrPassed += 1

        if timing_plot:
            timing_plot_report = TempXMLElement("timing_plot")
            timing_plot_report.appendTextNode("{0}/" + os.path.basename(timing_plot))
            simulation_report.appendChild(timing_plot_report)

        return success

    def _write_local_plot_summary(self):
        plots = sorted(pathlib.Path(self.dirname).glob("*.png"))
        if not plots:
            return

        summary_path = pathlib.Path(self.dirname) / "plot-summary.html"
        items = []
        for plot in plots:
            items.append(
                "    <figure>\n"
                f"      <img src=\"{plot.name}\" alt=\"{plot.name}\">\n"
                f"      <figcaption>{plot.name}</figcaption>\n"
                "    </figure>"
            )

        html = (
            "<!doctype html>\n"
            "<html lang=\"en\">\n"
            "<head>\n"
            "  <meta charset=\"utf-8\">\n"
            f"  <title>{self.simname} Plot Summary</title>\n"
            "  <style>\n"
            "    body { font-family: sans-serif; margin: 1.5rem; }\n"
            "    .grid { display: grid; grid-template-columns: repeat(2, 10cm); gap: 1rem; }\n"
            "    figure { margin: 0; width: 10cm; }\n"
            "    img { width: 10cm; height: 10cm; object-fit: contain; border: 1px solid #ccc; }\n"
            "    figcaption { margin-top: 0.4rem; font-size: 0.85rem; word-break: break-word; }\n"
            "  </style>\n"
            "</head>\n"
            "<body>\n"
            f"  <h1>{self.simname} Plot Summary</h1>\n"
            "  <div class=\"grid\">\n"
            + "\n".join(items)
            + "\n  </div>\n"
            "</body>\n"
            "</html>\n"
        )

        summary_path.write_text(html, encoding="utf-8")

    def _parse_timing_file(self, timing_path):
        total_wall = None
        timers = {}
        in_detail_table = False

        with open(timing_path, "r", encoding="utf-8") as stream:
            for raw_line in stream:
                line = raw_line.rstrip("\n")
                stripped = line.strip()
                if not stripped or stripped.startswith("="):
                    continue

                if stripped.startswith("ranks  Wall max"):
                    in_detail_table = True
                    continue

                if not in_detail_table:
                    match = re.match(r"^(.*?)\s+(\d+)\s+([0-9.eE+-]+)\s*$", stripped)
                    if match and match.group(1).strip().strip(".") == "mainTimer":
                        total_wall = float(match.group(3))
                    continue

                match = re.match(
                    r"^(.*?)\s+(\d+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s*$",
                    stripped,
                )
                if not match:
                    continue

                name = match.group(1).strip().strip(".")
                timers[name] = {
                    "ranks": int(match.group(2)),
                    "max": float(match.group(3)),
                    "min": float(match.group(4)),
                    "avg": float(match.group(5)),
                }

        return total_wall, timers

    def _classify_timer(self, name):
        if name in {"Write Stat", "Write H5-File"}:
            return "I/O"
        if name in {"scatter", "gather", "fillHalo", "accumulateHalo"}:
            return "communication"
        if (
            name.startswith("TIntegration")
            or name in {"particleBC", "External field eval.", "updateParticle"}
        ):
            return "tracking/integration"
        return "orchestration"

    def _select_dominant_timers(self, total_wall, timers):
        if not total_wall or total_wall <= 0.0:
            return []

        selected = []
        cumulative = 0.0
        for name, values in sorted(timers.items(), key=lambda item: item[1]["avg"], reverse=True):
            if name == "mainTimer":
                continue
            selected.append((name, values))
            cumulative += values["avg"]
            if cumulative >= 0.8 * total_wall:
                break
        return selected

    def _write_timing_overview(self):
        timing_path = pathlib.Path(self.dirname) / "timing.dat"
        reference_timing_path = pathlib.Path(self.dirname) / "reference" / "timing.dat"
        if not timing_path.is_file() or not reference_timing_path.is_file():
            return False

        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            from matplotlib.patches import Patch
        except ModuleNotFoundError:
            return False

        total_wall, timers = self._parse_timing_file(timing_path)
        if not timers:
            return False
        timers.pop("mainTimer", None)

        _, reference_timers = self._parse_timing_file(reference_timing_path)
        reference_timers.pop("mainTimer", None)
        selected = self._select_dominant_timers(total_wall, timers)
        if not selected:
            return False

        color_map = {
            "I/O": "#4C78A8",
            "communication": "#F58518",
            "tracking/integration": "#54A24B",
            "orchestration": "#B279A2",
        }

        labels = []
        averages = []
        lower_errors = []
        upper_errors = []
        colors = []
        delta_labels = []

        for name, values in selected:
            timer_class = self._classify_timer(name)
            labels.append(name)
            averages.append(values["avg"])
            if values["ranks"] == 1:
                lower_errors.append(0.0)
                upper_errors.append(0.0)
            else:
                lower_errors.append(max(values["avg"] - values["min"], 0.0))
                upper_errors.append(max(values["max"] - values["avg"], 0.0))
            colors.append(color_map[timer_class])

            ref_values = reference_timers.get(name)
            if ref_values and ref_values["avg"] != 0.0:
                delta_pct = 100.0 * (values["avg"] - ref_values["avg"]) / ref_values["avg"]
                delta_labels.append(rf"$\Delta$ {delta_pct:+.1f}%")
            else:
                delta_labels.append("n/a")

        cm_to_inch = 1.0 / 2.54
        plt.style.use("default")
        plt.rcParams.update(
            {
                "font.size": 10,
                "axes.titlesize": 10,
                "axes.labelsize": 10,
                "xtick.labelsize": 9,
                "ytick.labelsize": 10,
                "legend.fontsize": 9,
            }
        )

        fig, ax = plt.subplots(figsize=(20.0 * cm_to_inch, 20.0 * cm_to_inch), dpi=200)
        xpos = list(range(len(labels)))
        error = [lower_errors, upper_errors]
        bars = ax.bar(
            xpos,
            averages,
            yerr=error,
            capsize=4,
            color=colors,
            edgecolor="black",
            linewidth=0.8,
        )

        ymax = max(values["max"] for _, values in selected)
        offset = 0.03 * ymax if ymax > 0 else 0.05
        for bar, label, upper in zip(bars, delta_labels, upper_errors):
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                bar.get_height() + upper + offset,
                label,
                ha="center",
                va="bottom",
                rotation=90,
            )

        ax.set_xticks(xpos)
        ax.set_xticklabels(labels, rotation=90, ha="center", va="top")
        ax.set_ylabel("Wall time [s]")
        ax.set_title("Timing Overview (timers covering 80% of Wall)")
        ax.grid(True, axis="y", linestyle="--", linewidth=0.7, alpha=0.5)

        legend_handles = [
            Patch(facecolor=color, edgecolor="black", label=timer_class)
            for timer_class, color in color_map.items()
        ]
        ax.legend(handles=legend_handles, loc="upper right")

        fig.tight_layout()
        output_path = pathlib.Path(self.dirname) / f"{self.simname}_timing-overview.png"
        fig.savefig(output_path, bbox_inches="tight")
        plt.close(fig)
        return str(output_path)

    def publish(self, plots_dir):
        if not plots_dir:
            return False
        pathlib.Path(plots_dir).mkdir(parents=True, exist_ok=True)
        for p in pathlib.Path(".").glob("*.png"):
            shutil.copy (p, plots_dir)

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
        test = test.split("#", 1)[0].rstrip()
        nameparams = str.split(test,"\"")
        var = nameparams[1]
        params = nameparams[2].split()
        rtest = 0
        if "stat" in test:
            rtest = stattest.StatTest(var, params[0], float(params[1]),
                                      self.dirname, self.simname, use_gnuplot=self.use_gnuplot)
        else:
            return None

        return rtest.checkResult(root)
