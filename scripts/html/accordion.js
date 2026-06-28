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
            updateResultSliders();
        });
    }

    setupResultSliders();
}

function setupResultSliders() {
    var sliders = document.getElementsByClassName("result-scroll-slider");
    var i;

    for (i = 0; i != sliders.length; i++) {
        (function(slider) {
            var wrapper = slider.parentElement.parentElement.nextElementSibling;
            if (!wrapper || wrapper.className.indexOf("result-table-scroll") === -1) {
                return;
            }

            slider.max = 1000;
            slider.addEventListener("input", function() {
                var maxScroll = Math.max(0, wrapper.scrollWidth - wrapper.clientWidth);
                wrapper.scrollLeft = maxScroll * (Number(slider.value) / Number(slider.max));
            });
            wrapper.addEventListener("scroll", function() {
                var maxScroll = Math.max(0, wrapper.scrollWidth - wrapper.clientWidth);
                slider.value = maxScroll > 0 ? Math.round((wrapper.scrollLeft / maxScroll) * Number(slider.max)) : 0;
            });
        })(sliders[i]);
    }

    updateResultSliders();
}

function updateResultSliders() {
    var sliders = document.getElementsByClassName("result-scroll-slider");
    var i;

    for (i = 0; i != sliders.length; i++) {
        var slider = sliders[i];
        var wrapper = slider.parentElement.parentElement.nextElementSibling;
        if (!wrapper || wrapper.className.indexOf("result-table-scroll") === -1) {
            continue;
        }

        slider.value = 0;
    }
}
