#!/usr/bin/python3

import os
import re
import math

from OpalRegressionTests.reporter import Reporter
from OpalRegressionTests.reporter import TempXMLElement

class StatTest:
    """
    A regression test based on ASCII SDDS format for beam statistics
    type files. There are two file extensions supported: ".stat" files
    of global statistical beam parameters and ".smb" files of single
    bunch statistics in multibunch simulations.
    Member data:
        - var: the variable to be checked.
        - quant: string that defines how the variable should be handled.
          Options are "last" and "avg"
        - eps: floating point tolerance (absolute)
        - name: name of the smb file to be checked
    """

    def __init__(self, var, quant, eps, prefix, name, suffix = ".stat"):
        self.var = var
        self.quant = quant
        self.eps = eps
        self.prefix = prefix
        self.name = name
        self.fname = os.path.join(self.prefix, self.name) + suffix
        self.reference_fname = os.path.join(self.prefix, "reference", self.name) + suffix
        
    def _report_broken_test(self, root):
        passed_report = TempXMLElement("state")
        passed_report.appendTextNode("broken")
        root.appendChild(passed_report)

        eps_report = TempXMLElement("eps")
        eps_report.appendTextNode("%s" % self.eps)
        root.appendChild(eps_report)

        delta_report = TempXMLElement("delta")
        delta_report.appendTextNode("-")
        root.appendChild(delta_report)
        self.last_result = {
            "type": "stat",
            "var": self.var,
            "mode": self.quant,
            "eps": str(self.eps),
            "delta": "-",
            "state": "broken",
            "plot": None,
        }
        return False
        
    def checkResult(self, root):
        """
        method performs a test for a stat-file variable "var"
        """
        rep = Reporter()
        val = 0

        root.addAttribute("type", "stat")
        root.addAttribute("var", self.var)
        root.addAttribute("mode", self.quant)
        
        if not os.path.isfile(self.fname):
            rep.appendReport("ERROR: no statfile %s \n" % self.name)
            rep.appendReport("\t Test %s(%s) broken \n" % (self.var,self.quant))
            return self._report_broken_test(root)
            
        self.opalRevision, self.path_length, self.values = self._readStatVariable(self.fname)
        self.refRevision, self.ref_path_length, self.ref_values = self._readStatVariable(self.reference_fname)

        if self.values == [] or self.ref_values == []:
            rep.appendReport("Error: unknown variable (%s) selected for stat test\n" % self.var)
            rep.appendReport("\t Test %s(%s) broken: %s (eps=%s) \n" % (self.var,self.quant,val,self.eps))
            return self._report_broken_test(root)

        if len(self.values) != len(self.ref_values):
            rep.appendReport("Error: size of stat variables (%s) dont agree!\n" % self.var)
            rep.appendReport("       size reference: %d, size simulation: %d\n" % (
                len(self.ref_values), len(self.values)))
            rep.appendReport("\t Test %s(%s) broken: %s (eps=%s) \n" % (
                self.var,self.quant,val,self.eps))
            return self._report_broken_test(root)


        if self.quant == "last":
            val = abs(self.values[-1] - self.ref_values[-1])

        elif self.quant == "avg":
            sum = 0.0
            for i in range(len(self.values)):
                sum += (self.values[i] - self.ref_values[i])**2
            val = (sum)**(0.5) / len(self.values)

        elif self.quant == "error":
            rep.appendReport("TODO: error norm\n")

        elif self.quant == "all":
            rep.appendReport("TODO: graph/all\n")

        else:
            rep.appendReport("Error: unknown quantity %s \n" % self.quant)

        #result generation
        passed_report = TempXMLElement("state")
        eps_report = TempXMLElement("eps")
        delta_report = TempXMLElement("delta")
        plot_report = TempXMLElement("plot")

        passed = False
        if val < self.eps:
            rep.appendReport("Test %s(%s) passed: %s (eps=%s) \n" % (self.var,self.quant,val,self.eps))
            passed_report.appendTextNode("passed")
            passed = True
        else:
            rep.appendReport("Test %s(%s) failed: %s (eps=%s) \n" % (self.var,self.quant,val,self.eps))
            passed_report.appendTextNode("failed")

        delta_report.appendTextNode("%s" % val)
        eps_report.appendTextNode("%s" % self.eps)

        root.appendChild(passed_report)
        root.appendChild(eps_report)
        root.appendChild(delta_report)

        plotfilename = self._plot()
        plot_rel = None
        if plotfilename:
            fname = os.path.basename(plotfilename)
            # Keep a stable relative path format for the HTML report:
            # plots/<simname>/<filename>
            plot_rel = "plots/{0}/" + fname
            plot_report.appendTextNode(plot_rel)
            root.appendChild(plot_report)

        self.last_result = {
            "type": "stat",
            "var": self.var,
            "mode": self.quant,
            "eps": str(self.eps),
            "delta": str(val),
            "state": ("passed" if passed else "failed"),
            "plot": (plot_rel.format(self.name) if plot_rel else None),
        }

        return passed

    def _readStatHeader(self, statfile):
        """
        parse header of .stat file (ASCII SDDS format)
        """
        header = {'number of lines': 0,
                  'columns': {},
                  'parameters': {}
        }
        numColumns = 0
        numScalars = 0
        readLines = 0
        with open(statfile, "r") as infile:
            lines = [line.rstrip('\n') for line in infile]

        i = 0
        end_of_header_reached = False
        while not end_of_header_reached:
            line = lines[i]

            if "&column" in line:
                column = ""
                while True:
                    column += line
                    if "&end" in line:
                        break
                    i += 1
                    line = lines[i]

                name = str.split(column, "name=")[1]
                name = str.split(name, ",")[0]
                unit = str.split(column, "units=")[1]
                unit = str.split(unit, ",")[0]

                header['columns'][name] = {'units': unit, 'column': len(header['columns'])}
                numColumns += 1

            elif "&parameter" in line:
                parameter = ""
                while True:
                    parameter += line
                    if "&end" in line:
                        break
                    i += 1
                    line = lines[i]

                name = str.split(parameter, "name=")[1]
                name = str.split(name, ",")[0]

                header['parameters'][name] = {'row': len(header['parameters'])}

            elif "&data" in line:
                while not "&end" in line:
                    i += 1
                    line = lines[i]
                end_of_header_reached = True

            i += 1

        header['number of lines'] = i

        return header

    def _readStatVariable(self, fname):
        """
        method parses a stat-file and returns found variables
        """
        header = self._readStatHeader(fname)
        readLines = header['number of lines']
        revLine = header['parameters']['revision']['row']
        numScalars = len(header['parameters'])
        sCol = header['columns']['s']['column']
        self.s_unit = header['columns'].get('s', {}).get('units', '')
        
        varCol = -1
        if self.var in header['columns']:
            varData = header['columns'][self.var]
            varCol = varData['column']
            self.var_unit = varData.get('units', '')
        else:
            return []
        with open(fname,"r") as infile:
            lines = [line.rstrip('\n') for line in infile]
    
        m = re.search(r'(.* git rev\. )#([A-Za-z0-9]{7})[A-Za-z0-9]*', lines[readLines + revLine])
        if m:
            revision = m.group(1) + m.group(2)
        else:
            revision = lines[readLines + revLine]

        path_length = [float(line.split()[sCol]) for line in lines[(readLines + numScalars):]]
        values = [float(line.split()[varCol]) for line in lines[(readLines + numScalars):]]
        return revision, path_length, values

    def _read_stat_file(self, stat_file, plot_file):
        header = self._readStatHeader(stat_file)
        readLines = header['number of lines']
        revLine = header['parameters']['revision']['row']
        numScalars = len(header['parameters'])
        sCol = header['columns']['s']['column']

        varCol = -1
        if self.var in header['columns']:
            varData = header['columns'][self.var]
            varCol = varData['column']
            self.var_unit = varData['units']

        if varCol == -1:
            print ("Error in genplot: Cannot find stat variable!")
            return False

        stat_data = [line.rstrip('\n') for line in open(stat_file)]

        m = re.search(r'(.* git rev\. )#([A-Za-z0-9]{7})[A-Za-z0-9]*', stat_data[readLines + revLine])
        if m:
            revision = m.group(1) + m.group(2)
        else:
            revision = stat_data[readLines + revLine]

        with open(plot_file,'w') as f:
            for line in stat_data[(readLines + numScalars):]:
                values = line.split()
                f.write(values[sCol] + "\t" + values[varCol] + "\n")

        return revision

    def _plot(self):
        # Matplotlib is intentionally imported lazily to keep startup fast and
        # to provide a clearer error if it's not installed.
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except Exception as e:
            rep = Reporter()
            rep.appendReport(f"ERROR: matplotlib not available ({e})\n")
            return ""

        _opalRevision, s1, y1 = self._readStatVariable(self.fname)
        _refRevision, s2, y2 = self._readStatVariable(self.reference_fname)
        if not s1 or not s2 or len(s1) != len(s2):
            return ""

        # Compute difference (generated - reference)
        diff = [a - b for a, b in zip(y1, y2)]

        varParts = str.split(self.var, "_")
        prettyVar = varParts[0]
        if len(varParts) == 2:
            prettyVar = varParts[0] + "(" + varParts[1] + ")"

        output_fname = os.path.join(self.prefix, self.name + "_" + self.var + ".png")

        # Use constrained layout to avoid tight_layout warnings with shared axes/gridspec.
        fig = plt.figure(figsize=(10.5, 6.5), dpi=140, constrained_layout=True)
        gs = fig.add_gridspec(2, 1, height_ratios=[3, 1], hspace=0.12)
        ax = fig.add_subplot(gs[0, 0])
        ax2 = fig.add_subplot(gs[1, 0], sharex=ax)

        ax.plot(s1, y1, lw=1.8, label="simulation")
        ax.plot(s2, y2, lw=1.8, label="reference")
        ax.set_ylabel(f"{prettyVar} [{getattr(self, 'var_unit', '').strip()}]".strip())
        ax.grid(True, alpha=0.25)
        ax.legend(loc="upper right", fontsize=8)
        ax.set_title(self.name)

        ax2.plot(s1, diff, lw=1.6, color="#ef4444", label="difference")
        ax2.axhline(0.0, lw=1.0, color="black", alpha=0.4)
        s_unit = getattr(self, "s_unit", "").strip()
        ax2.set_xlabel(f"s [{s_unit}]" if s_unit else "s")
        var_unit = getattr(self, "var_unit", "").strip()
        ax2.set_ylabel(f"Δ [{var_unit}]" if var_unit else "Δ")
        ax2.grid(True, alpha=0.25)

        fig.savefig(output_fname)
        plt.close(fig)

        return output_fname
