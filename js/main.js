(function () {
  "use strict";

  /* ----- mobile nav ----- */
  var nav = document.getElementById("nav");
  var toggle = document.getElementById("navToggle");
  toggle.addEventListener("click", function () {
    var open = nav.classList.toggle("open");
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
  });
  nav.addEventListener("click", function (e) {
    if (e.target.tagName === "A") nav.classList.remove("open");
  });

  /* ----- reveal on scroll ----- */
  var observer = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("in");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.18, rootMargin: "0px 0px -40px 0px" }
  );
  document.querySelectorAll(".reveal, .report-card").forEach(function (el) {
    observer.observe(el);
  });

  /* ----- copy counter-offer ----- */
  var copyBtn = document.getElementById("copyBtn");
  var counterMsg = document.getElementById("counterMsg");
  if (copyBtn && counterMsg) {
    copyBtn.addEventListener("click", function () {
      var text = counterMsg.textContent.replace(/^["“]|["”]$/g, "");
      navigator.clipboard.writeText(text).then(
        function () {
          copyBtn.textContent = "Copied";
          setTimeout(function () {
            copyBtn.textContent = "Copy message";
          }, 1800);
        },
        function () {
          copyBtn.textContent = "Select & copy manually";
        }
      );
    });
  }

  /* ----- waitlist form ----- */
  var form = document.getElementById("joinForm");
  var done = document.getElementById("joinDone");
  var emailInput = document.getElementById("joinEmail");
  var cfg = window.CONTRAX_CONFIG || {};

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var email = emailInput.value.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      emailInput.focus();
      emailInput.style.borderColor = "#BE4B33";
      return;
    }
    emailInput.style.borderColor = "";

    var finish = function () {
      form.hidden = true;
      done.hidden = false;
    };

    if (cfg.WAITLIST_ENDPOINT) {
      fetch(cfg.WAITLIST_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ email: email })
      })
        .then(finish)
        .catch(finish);
    } else {
      // No endpoint configured yet — see js/config.example.js and README.
      console.warn("Contrax: WAITLIST_ENDPOINT not set; signup not persisted.");
      try {
        var list = JSON.parse(localStorage.getItem("contrax_waitlist") || "[]");
        list.push({ email: email, at: new Date().toISOString() });
        localStorage.setItem("contrax_waitlist", JSON.stringify(list));
      } catch (err) {}
      finish();
    }
  });
})();
