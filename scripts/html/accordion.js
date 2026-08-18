function setup() {
    var acc = document.getElementsByClassName("accordion");
    var i;

    for (i = 0; i != acc.length; i++) {
        acc[i].addEventListener("click", function() {
            this.classList.toggle("active");
            var panel = this.nextElementSibling;
            if (panel.style.maxHeight) {
                panel.style.maxHeight = null;
            } else {
                panel.style.maxHeight = panel.scrollHeight + "px";
            }
            updatePanelHeight(panel);
        });
    }

    setupPlotBrowsers();
}

function setupPlotBrowsers() {
    var browsers = document.getElementsByClassName("plot-browser");
    var i;

    for (i = 0; i != browsers.length; i++) {
        setupPlotBrowser(browsers[i]);
    }
}

function setupPlotBrowser(browser) {
    var slider = browser.getElementsByClassName("plot-selector-slider")[0];
    var frames = browser.getElementsByClassName("plot-frame");
    var counter = browser.getElementsByClassName("plot-counter")[0];
    var title = browser.getElementsByClassName("plot-title")[0];

    if (!slider || frames.length === 0) {
        return;
    }

    slider.max = frames.length - 1;
    slider.addEventListener("input", function() {
        showSelectedPlot(browser);
    });
    showSelectedPlot(browser);
}

function showSelectedPlot(browser) {
    var slider = browser.getElementsByClassName("plot-selector-slider")[0];
    var frames = browser.getElementsByClassName("plot-frame");
    var counter = browser.getElementsByClassName("plot-counter")[0];
    var title = browser.getElementsByClassName("plot-title")[0];
    var index = Math.max(0, Math.min(Number(slider.value), frames.length - 1));
    var i;

    slider.value = index;
    for (i = 0; i != frames.length; i++) {
        frames[i].classList.toggle("active-plot", i === index);
    }

    if (counter) {
        counter.textContent = (index + 1) + " / " + frames.length;
    }
    if (title) {
        title.textContent = frames[index].getAttribute("data-plot-title") || "";
    }

    updatePanelHeight(browser.closest(".panel"));
}

function updatePanelHeight(panel) {
    if (panel && panel.style.maxHeight) {
        panel.style.maxHeight = panel.scrollHeight + "px";
    }
}
