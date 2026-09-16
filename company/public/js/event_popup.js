// company/public/js/event-popup.js
// Full dynamic Event Popup (uses same theme + effects as your birthday script)
// Only triggers for Event Popup doctype via company.company.api.get_today_event
// No birthday logic is included (per your request).

(function() {
    // ---------------------------
    // CONFIG
    // ---------------------------
    const API_METHOD = "company.company.api.get_today_event";
    // Fallback audio file (keeps your original birthday song path as fallback)
    const FALLBACK_AUDIO = "";

    // ---------------------------
    // UTILS
    // ---------------------------
    const isGuest = () => (window.frappe && frappe.session && frappe.session.user === "Guest");

    function safeCreateAudio(src) {
        if (!src) src = FALLBACK_AUDIO;
        try {
            const a = new Audio(src);
            a.volume = 0.7;
            return a;
        } catch (e) {
            return null;
        }
    }

    function resolveMusicUrl(musicField) {
        // The Event Popup music field may be:
        // - a full url (/files/xxx)
        // - a filename like "Birthday_Song.mp3" (attached file name)
        // - empty/undefined
        if (!musicField) return FALLBACK_AUDIO;
        if (typeof musicField !== "string") return FALLBACK_AUDIO;

        // If already looks like a files path, return as-is
        if (musicField.startsWith("/files/") || musicField.startsWith("/private/files/") || musicField.startsWith("http")) {
            return musicField;
        }

        // Otherwise assume it's stored as a filename, create a /files/ URL
        return "/files/" + musicField;
    }

    // ---------------------------
    // CORE: fetch today's event and show popup
    // ---------------------------
    function initEventPopup() {
        if (!window.frappe || isGuest()) return;

        frappe.after_ajax(() => {
            try {
                frappe.call({
                    method: API_METHOD,
                    callback: function(r) {
                        if (!r || !r.message) return;

                        const ev = r.message;

                        // require enabled event (server should only return enabled, but double-check)
                        if (ev.enabled === 0 || ev.enabled === "0") return;

                        // create stable key per event per date to avoid duplicates
                        const dateKey = new Date().toISOString().split("T")[0];
                        const eventNameSafe = (ev.event_name || ev.title || "event").replace(/\s+/g, "_").toLowerCase();
                        const storageKey = `event_popup_shown_${eventNameSafe}_${dateKey}`;
                        if (localStorage.getItem(storageKey)) return; // already shown today

                        // mark shown (we still allow re-open if needed in same session if you remove key)
                        localStorage.setItem(storageKey, "1");

                        // Prepare audio (resolve URL and create Audio object)
                        const musicUrl = resolveMusicUrl(ev.music);
                        window.eventAudio = safeCreateAudio(musicUrl);

                        // Trigger audio + popup on single user click
                        createUnlockClick(ev);



                    }
                });
            } catch (e) {
                // fail silently
                console.error("Event Popup: API call failed", e);
            }
        });
    }

    function createUnlockClick(ev) {

        const trigger = document.createElement("div");
        trigger.id = "eventClickUnlock";
        trigger.style = `
        position: fixed;
        inset: 0;
        z-index: 999999999;
        cursor: pointer;
        background: transparent;
    `;
        document.body.appendChild(trigger);

        trigger.addEventListener("click", async () => {

            // 1) Try to play audio
            try {
                await window.eventAudio.play();
            } catch (e) {
                console.warn("Audio unlock failed:", e);
            }

            // 2) Remove unlock layer
            trigger.remove();

            // 3) Show popup immediately
            showDynamicEventPopup(ev);

            // 4) Start effects
            startEffects();

        }, {
            once: true
        });
    }


    // ---------------------------
    // POPUP UI (same theme as your birthday popup)
    // ---------------------------
    function showDynamicEventPopup(ev) {

        const overlay = document.createElement("div");
        overlay.id = "event-overlay";
        overlay.style = `
            position: fixed;
            inset: 0;
            background: rgba(10,10,35,0.6);
            display: flex;
            align-items: center;
            justify-content: center;
            backdrop-filter: blur(6px);
            z-index: 999999;
            animation: fadeIn .6s ease-out;
            cursor: pointer;
        `;

        const card = document.createElement("div");
        card.style = `
            padding: 35px 45px;
            background: rgba(255,255,255,0.14);
            border: 2px solid gold;
            border-radius: 22px;
            color: #fff;
            text-align: center;
            backdrop-filter: blur(15px);
            animation: popIn .6s ease-out;
            cursor: pointer;
            max-width: 820px;
            box-sizing: border-box;
        `;

        // render dynamic content (support placeholder {{name}} though not required by your doctype)
        const titleText = (ev.title || "🎉 Celebration!");
        const msgText = (ev.message || "");

        card.innerHTML = `
            <h1 style="font-size:42px;color:#ffdd55;margin-bottom:10px;line-height:1.05;">
                ${escapeHtml(titleText)}
            </h1>

            <p style="font-size:20px;margin-top:6px;line-height:1.4;">
                ${escapeHtml(msgText).replace(/\n/g, "<br>")}
            </p>

            <p style="font-size:14px;color:#eee;margin-top:18px;">
                Tap anywhere to close
            </p>
        `;

        overlay.appendChild(card);
        document.body.appendChild(overlay);

        // Close handler — stop music + effects + remove DOM
        overlay.addEventListener("click", () => {
            closeAllEffects();
            // stop eventAudio if present (the birthday code stops birthdayAudio; here we clean both)
            try {
                window.eventAudio && window.eventAudio.pause();
                window.eventAudio && (window.eventAudio.currentTime = 0);
            } catch (e) {}
        });
    }


    // ---------------------------
    // REUSE YOUR EFFECTS (fireworks, confetti, balloons)
    // Copied from your existing working code (keeps same look/behaviour)
    // ---------------------------
    let fireworksInterval, confettiInterval, balloonInterval, stopFx = false;

    function closeAllEffects() {
        try {
            window.eventAudio && window.eventAudio.pause();
            window.eventAudio && (window.eventAudio.currentTime = 0);
        } catch (e) {}
        try {
            window.birthdayAudio && window.birthdayAudio.pause();
            window.birthdayAudio && (window.birthdayAudio.currentTime = 0);
        } catch (e) {}

        stopFx = true;

        clearInterval(fireworksInterval);
        clearInterval(confettiInterval);
        clearInterval(balloonInterval);

        document.getElementById("event-overlay")?.remove();
        document.getElementById("birthday-overlay")?.remove();
        document.getElementById("fireworksCanvas")?.remove();

        document.querySelectorAll(".auto-balloon").forEach(e => e.remove());
        document.querySelectorAll(".auto-confetti").forEach(e => e.remove());
    }

    function startEffects() {
        stopFx = false;
        createFireworks();
        launchConfetti();
        launchBalloons();
    }

    function createFireworks() {
        const canvas = document.createElement("canvas");
        canvas.id = "fireworksCanvas";
        canvas.style = `
            position: fixed; top: 0; left: 0;
            width: 100vw; height: 100vh;
            pointer-events: none;
            z-index: 1999998;
        `;
        document.body.appendChild(canvas);

        const ctx = canvas.getContext("2d");
        canvas.width = innerWidth;
        canvas.height = innerHeight;

        const particles = [];
        const rand = (min, max) => Math.random() * (max - min) + min;

        function explode(x, y) {
            for (let i = 0; i < 40; i++) {
                particles.push({
                    x,
                    y,
                    size: rand(2, 4),
                    speedX: rand(-5, 5),
                    speedY: rand(-5, 5),
                    color: `hsl(${rand(0,360)},100%,60%)`,
                    life: 60
                });
            }
        }

        fireworksInterval = setInterval(() => {
            if (stopFx) return;
            explode(rand(100, canvas.width - 100), rand(50, canvas.height / 1.5));
        }, 700);

        function animate() {
            if (stopFx) return;
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            particles.forEach((p, i) => {
                p.x += p.speedX;
                p.y += p.speedY;
                p.life--;

                ctx.fillStyle = p.color;
                ctx.beginPath();
                ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
                ctx.fill();

                if (p.life <= 0) particles.splice(i, 1);
            });

            requestAnimationFrame(animate);
        }

        animate();
    }

    function launchConfetti() {
        const colors = ["#ff4d6d", "#ffdd57", "#5dd39e", "#7ea9e1", "#c77dff"];

        confettiInterval = setInterval(() => {
            if (stopFx) return;

            const conf = document.createElement("div");
            conf.classList.add("auto-confetti");

            conf.style = `
                width: 12px; height: 12px;
                background: ${colors[Math.floor(Math.random()*colors.length)]};
                position: fixed;
                top: -20px; left: ${Math.random()*100}vw;
                opacity: 0.9;
                animation: confettiFall 3s linear forwards;
                z-index: 1000002;
                transform: rotate(${Math.random()*360}deg);
            `;
            document.body.appendChild(conf);

            setTimeout(() => conf.remove(), 3500);
        }, 100);
    }

    function launchBalloons() {
        const colors = ["#ff4d6d", "#ff922b", "#4cc9f0", "#70e000", "#b5179e", "#f9c80e"];

        if (!document.getElementById("balloonCSS")) {
            const css = document.createElement("style");
            css.id = "balloonCSS";
            css.innerHTML = `
                @keyframes floatRealistic {
                    0% { transform: translateY(0) rotate(-3deg); }
                    50% { transform: translateY(-45vh) rotate(3deg); }
                    100% { transform: translateY(-75vh) rotate(-2deg); }
                }
                @keyframes threadFall {
                    0% { opacity: 1; transform: translateY(0); }
                    100% { opacity: 0; transform: translateY(60vh); }
                }
                @keyframes shardFall {
                    0% { opacity: 1; }
                    100% { opacity: 0; transform: translateY(150px) rotate(180deg); }
                }
            `;
            document.head.appendChild(css);
        }

        balloonInterval = setInterval(() => {
            if (stopFx) return;

            const balloon = document.createElement("div");
            const color = colors[Math.floor(Math.random() * colors.length)];
            const left = Math.random() * 80;

            balloon.className = "auto-balloon";
            balloon.style = `
                position: fixed;
                bottom: -160px;
                left: ${left}%;
                width: 70px;
                height: 90px;
                background: ${color};
                border-radius: 50% 50% 45% 45%;
                box-shadow: inset -20px -14px 20px rgba(0,0,0,0.25);
                animation: floatRealistic 5.5s ease-out forwards;
                z-index: 1000002;
                pointer-events: none;
            `;

            const shine = document.createElement("div");
            shine.style = `
                position: absolute;
                top: 15px; left: 18px;
                width: 22px; height: 40px;
                background: rgba(255,255,255,.55);
                border-radius: 50%;
            `;

            const knot = document.createElement("div");
            knot.style = `
                position: absolute;
                bottom: -10px; left: 50%;
                width: 16px; height: 12px;
                background: ${color};
                transform: translateX(-50%);
                border-radius: 40% 40% 60% 60%;
            `;

            const thread = document.createElement("div");
            thread.style = `
                position: absolute;
                bottom: -70px; left: 50%;
                width: 2px; height: 80px;
                transform: translateX(-50%);
            `;

            for (let i = 0; i < 6; i++) {
                const seg = document.createElement("div");
                seg.style = `
                    width: 2px; height: 15px;
                    margin: 0 auto;
                    background: #ffffff31;
                    transform: rotate(${(Math.random()*20 - 10).toFixed(1)}deg);
                `;
                thread.appendChild(seg);
            }

            balloon.appendChild(shine);
            balloon.appendChild(knot);
            balloon.appendChild(thread);
            document.body.appendChild(balloon);

            setTimeout(() => {
                balloon.style.background = "transparent";
                shine.style.opacity = 0;
                knot.style.background = "transparent";

                for (let i = 0; i < 8; i++) {
                    const shard = document.createElement("div");
                    shard.style = `
                        position: absolute;
                        width: 12px; height: 12px;
                        background: ${color};
                        top: 40px; left: 32px;
                        border-radius: 2px;
                        animation: shardFall .7s ease-out forwards;
                    `;
                    balloon.appendChild(shard);
                }

                thread.style.animation = "threadFall 1.2s linear forwards";

                setTimeout(() => balloon.remove(), 1200);
            }, 3400);

        }, 600);
    }

    // ---------------------------
    // GLOBAL CSS (popIn / fadeIn / confetti)
    // ---------------------------
    (function injectGlobalStyles() {
        if (document.getElementById("event-popup-global-style")) return;
        const style = document.createElement("style");
        style.id = "event-popup-global-style";
        style.innerHTML = `
            @keyframes popIn {0%{opacity:0;transform:scale(.6);}100%{opacity:1;transform:scale(1);} }
            @keyframes fadeIn { from{opacity:0;} to{opacity:1;} }
            @keyframes confettiFall {
                to { transform: translateY(120vh) rotate(720deg); }
            }
        `;
        document.head.appendChild(style);
    })();

    // ---------------------------
    // Escape helper for XSS safety (we'll still allow basic text + line breaks)
    // ---------------------------
    function escapeHtml(unsafe) {
        if (unsafe === null || unsafe === undefined) return "";
        return String(unsafe)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // Initialize
    initEventPopup();

})();