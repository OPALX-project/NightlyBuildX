<?xml version="1.0" encoding="ISO-8859-1"?>
<xsl:stylesheet version="1.0"
                xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

  <xsl:template match="/">
    <html>
      <head>
        <title>OPALX Regression Test Results</title>
        <link rel="stylesheet" href="nightlybuildx.css"/>
        <style type="text/css">
          .no-hover {text-decoration:none; color:#000;}
          .no-hover:hover {text-decoration:none; color:#000;}
        </style>
        <script type="text/javascript" src="accordion.js"></script>
      </head>
      <body onLoad="setup()">
        <main>
        <h1>OPALX Regression Test Results</h1>
        <h2><a name="test_revision" class="no-hover">Revisions</a></h2>
        <table>
          <tr>
            <th>Date</th>
            <th>Code</th>
            <th>Tests</th>
          </tr>
          <tr>
            <xsl:variable name="code_hash" select="Tests/Revisions/code_full"/>
            <xsl:variable name="tests_hash" select="Tests/Revisions/tests_full"/>
            <td style="padding: 0px 10px 0px 10px">
              <xsl:value-of select="Tests/Date/start"/>
            </td>
            <td style="padding: 0px 10px 0px 10px">
              <a href="https://github.com/OPALX-project/OPALX/commit/{$code_hash}" target="_blank">
                <xsl:value-of select="Tests/Revisions/code"/>
              </a>
            </td>
            <td style="padding: 0px 10px 0px 10px">
              <a href="https://github.com/OPALX-project/regression-tests-x/commit/{$tests_hash}" target="_blank">
                <xsl:value-of select="Tests/Revisions/tests"/>
              </a>
            </td>
          </tr>
        </table>
        <xsl:if test="Tests/RunMetadata">
          <h2><a name="run_metadata" class="no-hover">Run Metadata</a></h2>
          <table style="margin-bottom: 25px">
            <tr>
              <th>Host</th>
              <th>Architecture</th>
              <th>Backend</th>
              <th>Ranks</th>
              <th>Threads</th>
              <th>Device</th>
            </tr>
            <tr>
              <td style="padding: 0px 10px 0px 10px"><xsl:value-of select="Tests/RunMetadata/host"/></td>
              <td style="padding: 0px 10px 0px 10px"><xsl:value-of select="Tests/RunMetadata/architecture"/></td>
              <td style="padding: 0px 10px 0px 10px"><xsl:value-of select="Tests/RunMetadata/backend"/></td>
              <td style="padding: 0px 10px 0px 10px"><xsl:value-of select="Tests/RunMetadata/mpi_ranks"/></td>
              <td style="padding: 0px 10px 0px 10px"><xsl:value-of select="Tests/RunMetadata/omp_threads"/></td>
              <td style="padding: 0px 10px 0px 10px"><xsl:value-of select="Tests/RunMetadata/device"/></td>
            </tr>
          </table>
        </xsl:if>
        <h2>Regression Tests</h2>
        <xsl:if test="count(Tests/Simulation/Test[state]) &gt; 0">
          <table style="margin-bottom: 25px">
            <tr>
              <th style="padding: 2px 16px 2px 16px;">Passed</th>
              <th style="padding: 2px 16px 2px 16px;">Broken</th>
              <th style="padding: 2px 16px 2px 16px;">Failed</th>
              <th style="padding: 2px 16px 2px 16px;">Total</th>
            </tr>
            <tr>
              <td style="text-align: center"><xsl:value-of select="count(Tests/Simulation/Test[state='passed'])"/></td>
              <td style="text-align: center"><xsl:value-of select="count(Tests/Simulation/Test[state='broken'])"/></td>
              <td style="text-align: center"><xsl:value-of select="count(Tests/Simulation/Test[state='failed'])"/></td>
              <td style="text-align: center"><xsl:value-of select="count(Tests/Simulation/Test)"/></td>
            </tr>
          </table>
        </xsl:if>
        <xsl:for-each select="Tests/Simulation">
          <xsl:variable name="simname" select="@name"/>
          <xsl:choose>
            <xsl:when test="count(Test[passed]) &gt; 0">
              <xsl:choose>
                <xsl:when test="count(Test) != count(Test[passed='true'])">
                  <button class="accordion fail">
                    <b style="margin-right:40px"><xsl:value-of select="@name"/></b>
                    [passed: <xsl:value-of select="count(Test[passed='true'])"/> | broken or failed: <xsl:value-of select="count(Test[passed='false'])"/> ]
                  </button>
                </xsl:when>
                <xsl:otherwise>
                  <button class="accordion">
                    <b style="margin-right:40px"><xsl:value-of select="@name"/></b>
                    [passed: <xsl:value-of select="count(Test[passed='true'])"/> | broken or failed: <xsl:value-of select="count(Test[passed='false'])"/> ]
                  </button>
                </xsl:otherwise>
              </xsl:choose>
            </xsl:when>
            <xsl:otherwise>
              <xsl:choose>
                <xsl:when test="count(Test) != count(Test[state='passed'])">
                  <button class="accordion fail"> <b style="margin-right:40px"><xsl:value-of select="@name"/></b>
                  [passed: <xsl:value-of select="count(Test[state='passed'])"/> | broken: <xsl:value-of select="count(Test[state='broken'])"/> | failed: <xsl:value-of select="count(Test[state='failed'])"/> ]
                  </button>
                </xsl:when>
                <xsl:otherwise>
                  <button class="accordion"> <b style="margin-right:40px"><xsl:value-of select="@name"/></b>
                  [passed: <xsl:value-of select="count(Test[state='passed'])"/> | broken: <xsl:value-of select="count(Test[state='broken'])"/> | failed: <xsl:value-of select="count(Test[state='failed'])"/> ]
                  </button>
                </xsl:otherwise>
              </xsl:choose>
            </xsl:otherwise>
          </xsl:choose>
          <div class="panel">
            <p>
              <!--<h3>Simulation: <xsl:value-of select="@name"/></h3>-->
              Description: <xsl:value-of select="@description"/>
              <div class="result-table-toolbar">
                <label>
                  Browse result columns
                  <input class="result-scroll-slider" type="range" min="0" max="1000" value="0"/>
                </label>
              </div>
              <div class="result-table-scroll">
              <table>
                <tr>
                  <th>Variable</th>
                  <th>Mode</th>
                  <th>Required Accuracy</th>
                  <th>Delta</th>
                  <th>Status</th>
                </tr>
                <xsl:for-each select="Test">
                  <xsl:choose>
                    <xsl:when test="contains(state,'passed') or contains(passed,'true')">
                      <tr>
                        <td><xsl:value-of select="@var"/></td>
                        <td><xsl:value-of select="@mode"/></td>
                        <td><xsl:value-of select="eps"/></td>
                        <td><xsl:value-of select="delta"/></td>
                        <td align="center"><img src="ok.png"/></td>
                      </tr>
                    </xsl:when>
                    <xsl:otherwise>
                      <tr bgcolor="#cdba2d">
                        <td><xsl:value-of select="@var"/></td>
                        <td><xsl:value-of select="@mode"/></td>
                        <td><xsl:value-of select="eps"/></td>
                        <td><xsl:value-of select="delta"/></td>
                        <td align="center"><img src="nok.png"/></td>
                      </tr>
                    </xsl:otherwise>
                  </xsl:choose>
                </xsl:for-each>
              </table>
              </div><br/>
              <xsl:for-each select="Test">
                <xsl:variable name="plotname" select="plot"/>
                <xsl:if test="$plotname">
                  <xsl:variable name="varname" select="@var"/>
                  <img class="plot-image" src="{plot}" alt="" title="" />
                  <br/><br/>
                </xsl:if>

              </xsl:for-each>
              <xsl:if test="timing_plot">
                <img class="plot-image" src="{timing_plot}" alt="" title="" />
                <br/><br/>
              </xsl:if>
              <br/>
            </p>
          </div>
        </xsl:for-each>
        </main>
      </body>
    </html>
  </xsl:template>

</xsl:stylesheet>
