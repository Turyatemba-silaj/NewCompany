(function () {
    const toggle = document.querySelector("[data-menu-toggle]");
    const nav = document.querySelector("[data-site-nav]");
    if (toggle && nav) {
        toggle.addEventListener("click", () => {
            const isOpen = nav.classList.toggle("open");
            toggle.setAttribute("aria-expanded", String(isOpen));
        });
    }

    document.querySelectorAll("[data-slider]").forEach((slider) => {
        const slides = Array.from(slider.querySelectorAll(".slide"));
        const dotsWrap = slider.querySelector("[data-slide-dots]");
        const prev = slider.querySelector("[data-slide-prev]");
        const next = slider.querySelector("[data-slide-next]");
        const slideIntervalMs = Number(slider.dataset.slideInterval || 9000);
        let index = 0;
        let timer = null;

        const dots = slides.map((_, dotIndex) => {
            const dot = document.createElement("button");
            dot.className = "slide-dot";
            dot.type = "button";
            dot.setAttribute("aria-label", `Go to slide ${dotIndex + 1}`);
            dot.addEventListener("click", () => show(dotIndex, true));
            if (dotsWrap) dotsWrap.appendChild(dot);
            return dot;
        });

        function show(nextIndex, userAction) {
            if (!slides.length) return;
            index = (nextIndex + slides.length) % slides.length;
            slides.forEach((slide, slideIndex) => {
                slide.classList.toggle("active", slideIndex === index);
            });
            dots.forEach((dot, dotIndex) => {
                dot.classList.toggle("active", dotIndex === index);
            });
            if (userAction) restart();
        }

        function start() {
            if (slides.length > 1 && !timer) {
                timer = window.setInterval(() => show(index + 1, false), slideIntervalMs);
            }
        }

        function stop() {
            if (timer) window.clearInterval(timer);
            timer = null;
        }

        function restart() {
            stop();
            start();
        }

        if (prev) prev.addEventListener("click", () => show(index - 1, true));
        if (next) next.addEventListener("click", () => show(index + 1, true));
        slider.addEventListener("mouseenter", stop);
        slider.addEventListener("mouseleave", start);
        show(0, false);
        start();
    });

    const serviceCopy = {
        guarding: {
            title: "Manned Guarding",
            body: "We place trained officers at client premises, track attendance, assign supervisors, and keep site records ready for review.",
            points: ["Access control and visitor management", "Day and night shift coverage", "Supervisor checklist and attendance records"],
        },
        patrols: {
            title: "Mobile Patrols",
            body: "Patrol teams and supervisors provide visible follow-up for client sites, including route checks, shift support, and escalation.",
            points: ["Scheduled patrol coverage", "Site visit documentation", "Rapid escalation to operations managers"],
        },
        response: {
            title: "Incident Response",
            body: "Incidents are recorded, investigated, reviewed, and escalated with clear reporting for clients and internal managers.",
            points: ["Incident notifications", "Investigation reports", "Closure notes and accountability trail"],
        },
        assets: {
            title: "Asset Protection",
            body: "Assigned equipment, site assets, stores, and issued-out items are tracked so responsibility stays visible.",
            points: ["Asset assignment reports", "Store accountability", "Vehicle and equipment detail records"],
        },
    };

    const detail = document.querySelector("[data-service-detail]");
    const serviceTabs = Array.from(document.querySelectorAll("[data-service-tab]"));
    const serviceCards = Array.from(document.querySelectorAll("[data-service-card]"));

    function setService(key) {
        const copy = serviceCopy[key];
        if (!copy || !detail) return;
        detail.innerHTML = `<h3>${copy.title}</h3><p>${copy.body}</p><ul>${copy.points.map((point) => `<li>${point}</li>`).join("")}</ul>`;
        serviceTabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.serviceTab === key));
        serviceCards.forEach((card) => card.classList.toggle("is-active", card.dataset.serviceCard === key));
    }

    serviceTabs.forEach((tab) => {
        tab.addEventListener("click", () => setService(tab.dataset.serviceTab));
    });
    serviceCards.forEach((card) => {
        card.addEventListener("click", () => setService(card.dataset.serviceCard));
    });
    if (detail) setService("guarding");

    document.querySelectorAll("[data-filter]").forEach((button) => {
        button.addEventListener("click", () => {
            const value = button.dataset.filter;
            const buttons = Array.from(button.parentElement.querySelectorAll("[data-filter]"));
            const cards = Array.from(document.querySelectorAll("[data-card-type]"));
            let visibleCount = 0;

            buttons.forEach((item) => item.classList.toggle("active", item === button));
            cards.forEach((card) => {
                const isVisible = value === "all" || card.dataset.cardType === value;
                card.style.display = isVisible ? "" : "none";
                if (isVisible) visibleCount += 1;
            });

            document.querySelectorAll("[data-empty-updates]").forEach((empty) => {
                empty.classList.toggle("is-hidden", visibleCount > 0);
            });
        });
    });

    document.querySelectorAll("[data-count-up]").forEach((item) => {
        const target = Number(item.dataset.countUp || 0);
        const duration = 900;
        const start = performance.now();

        function tick(now) {
            const progress = Math.min((now - start) / duration, 1);
            item.textContent = Math.round(target * progress).toLocaleString();
            if (progress < 1) window.requestAnimationFrame(tick);
        }

        window.requestAnimationFrame(tick);
    });
})();
