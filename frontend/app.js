/* ═══════════════════════════════════════════════
   ElectionGuide AI — Frontend Application
   Powered by Google ADK + Gemini 2.5 Flash
   ═══════════════════════════════════════════════ */

const API = window.location.origin;
let SESSION_ID = localStorage.getItem("eg_session") || crypto.randomUUID();
localStorage.setItem("eg_session", SESSION_ID);
let isSending = false;

/* ─── Topic Cards (populated dynamically) ─── */
const TOPICS = [
    { icon: "calendar_today", title: "Election Timeline", desc: "Schedules, notification dates, and counting deadlines across all states.", query: "Explain the complete election timeline in India" },
    { icon: "assignment_ind", title: "Voter Registration", desc: "Step-by-step guide for new enrollment, correction of details, and booth search.", query: "How do I register to vote in India?" },
    { icon: "account_balance", title: "Nomination Process", desc: "Candidate criteria, affidavit scrutiny, and the legal framework for representation.", query: "Explain the nomination process for Indian elections" },
    { icon: "how_to_vote", title: "Polling Day Guide", desc: "From EVM operation to VVPAT verification — know your rights at the booth.", query: "What happens on polling day in India?" },
    { icon: "analytics", title: "Vote Counting", desc: "Counting day procedures, EVM tallying, and official result declaration.", query: "How are votes counted in Indian elections?" },
    { icon: "verified", title: "Check Eligibility", desc: "Verify your eligibility to vote based on current constitutional provisions.", query: "Am I eligible to vote? I am 19 years old, an Indian citizen" }
];

/* ─── DEMO flow questions ─── */
const DEMO_QUESTIONS = [
    "What are the key stages in the Indian election timeline?",
    "Check eligibility: I am 17 years old, Indian citizen"
];

/* ─── Init ─── */
document.addEventListener("DOMContentLoaded", () => {
    renderTopics();
    const input = document.getElementById("chat-input");
    if (input) {
        input.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
        });
    }
});

/* ─── Render topic cards into grid ─── */
function renderTopics() {
    const grid = document.getElementById("topics-grid");
    if (!grid) return;
    grid.innerHTML = TOPICS.map((t, i) => `
        <div onclick="askTopic(${i})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();askTopic(${i})}" role="button" tabindex="0" aria-label="${t.title}: ${t.desc}" class="glass-panel p-5 md:p-8 rounded-xl border-t border-white/10 hover:translate-y-[-8px] transition-transform duration-500 group cursor-pointer focus:ring-2 focus:ring-primary focus:outline-none">
            <div class="w-12 h-12 md:w-14 md:h-14 rounded-full bg-surface-container-high flex items-center justify-center mb-4 md:mb-6 text-2xl md:text-3xl group-hover:bg-primary/20 transition-colors duration-500">
                <span class="material-symbols-outlined text-primary" aria-hidden="true">${t.icon}</span>
            </div>
            <h3 class="text-base md:text-xl font-headline font-bold mb-2 md:mb-3">${t.title}</h3>
            <p class="text-on-surface-variant text-xs md:text-sm leading-relaxed mb-4 md:mb-6">${t.desc}</p>
            <span class="text-[10px] md:text-xs font-label uppercase tracking-widest text-primary flex items-center gap-2 group-hover:gap-4 transition-all">Ask AI <span class="material-symbols-outlined text-sm" aria-hidden="true">arrow_forward</span></span>
        </div>
    `).join("");
}

/* ─── Topic click handler ─── */
function askTopic(idx) {
    scrollToChat();
    const q = TOPICS[idx].query;
    document.getElementById("chat-input").value = q;
    // Firebase Analytics — track topic card interaction
    if (window.firebaseLogEvent) window.firebaseLogEvent("topic_click", { topic: TOPICS[idx].title });
    sendMessage();
}

/* ─── Scroll to chat ─── */
function scrollToChat() {
    document.getElementById("chat-section").scrollIntoView({ behavior: "smooth", block: "center" });
}

/* ─── Send a message ─── */
async function sendMessage() {
    const input = document.getElementById("chat-input");
    const text = input.value.trim();
    if (!text || isSending) return;
    input.value = "";
    isSending = true;
    setBtnState(true);

    appendUserMsg(text);
    const typingEl = showTyping();

    try {
        const res = await fetch(`${API}/api/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: text, session_id: SESSION_ID })
        });
        const data = await res.json();
        removeTyping(typingEl);

        if (res.status === 429) {
            // Rate limited — friendly message + cooldown
            appendBotMsg("⏳ The AI is processing many requests right now. Please wait a moment and try again.");
            cooldownInput(8000);
            if (window.firebaseLogEvent) window.firebaseLogEvent("rate_limited", { query: text.substring(0, 50) });
        } else if (data.error) {
            appendBotMsg("⚠️ " + data.error);
        } else {
            appendBotMsg(data.response, data.tool_used);
            // Firebase Analytics — track successful chat
            if (window.firebaseLogEvent) window.firebaseLogEvent("chat_message", { tool_used: data.tool_used || "none", cached: data.cached || false });
        }
    } catch (err) {
        removeTyping(typingEl);
        appendBotMsg("⚠️ Connection error. Please ensure the backend is running.");
    }
    isSending = false;
    setBtnState(false);
}

/* ─── Message rendering ─── */
function appendUserMsg(text) {
    const container = document.getElementById("chat-messages");
    const el = document.createElement("div");
    el.className = "flex justify-end msg-animate";
    el.innerHTML = `
        <div class="max-w-[85%] md:max-w-[60%] bg-primary-container text-on-primary-container px-5 md:px-6 py-3 md:py-4 rounded-2xl rounded-tr-none shadow-xl">
            <p class="font-body text-sm md:text-[15px] leading-relaxed">${escapeHtml(text)}</p>
        </div>`;
    container.appendChild(el);
    container.scrollTop = container.scrollHeight;
}

function appendBotMsg(md, toolName) {
    const container = document.getElementById("chat-messages");
    const el = document.createElement("div");
    el.className = "flex justify-start items-start gap-3 msg-animate";

    let toolBadge = "";
    if (toolName) {
        toolBadge = `<div class="flex items-center gap-2 mb-3">
            <div class="px-2 py-0.5 bg-tertiary-container/30 text-tertiary text-[10px] rounded uppercase font-bold tracking-widest shimmer">🔧 ${escapeHtml(toolName)}</div>
        </div>`;
    }

    const htmlContent = renderMarkdown(md);

    el.innerHTML = `
        <div class="w-8 h-8 rounded-full bg-surface-container-highest flex items-center justify-center shrink-0 border border-outline-variant/30">
            <span class="material-symbols-outlined text-xs text-primary">smart_toy</span>
        </div>
        <div class="max-w-[85%] md:max-w-[70%] bg-surface-container-lowest/80 border border-outline-variant/10 px-5 md:px-7 py-4 md:py-5 rounded-2xl rounded-tl-none bot-msg">
            ${toolBadge}
            <div class="text-sm md:text-[15px] leading-relaxed">${htmlContent}</div>
        </div>`;
    container.appendChild(el);
    container.scrollTop = container.scrollHeight;
}

function showTyping() {
    const container = document.getElementById("chat-messages");
    const el = document.createElement("div");
    el.className = "flex justify-start items-start gap-3 msg-animate";
    el.id = "typing-indicator";
    el.innerHTML = `
        <div class="w-8 h-8 rounded-full bg-surface-container-highest flex items-center justify-center shrink-0 border border-outline-variant/30">
            <span class="material-symbols-outlined text-xs text-primary">smart_toy</span>
        </div>
        <div class="bg-surface-container-lowest/80 border border-outline-variant/10 px-6 py-4 rounded-2xl rounded-tl-none flex gap-1.5 items-center">
            <span class="w-2 h-2 rounded-full bg-primary typing-dot"></span>
            <span class="w-2 h-2 rounded-full bg-primary typing-dot"></span>
            <span class="w-2 h-2 rounded-full bg-primary typing-dot"></span>
        </div>`;
    container.appendChild(el);
    container.scrollTop = container.scrollHeight;
    updateStatus("Thinking...");
    return el;
}

function removeTyping(el) {
    if (el && el.parentNode) el.parentNode.removeChild(el);
    updateStatus("Online");
}

/* ─── Clear chat ─── */
function clearChat() {
    SESSION_ID = crypto.randomUUID();
    localStorage.setItem("eg_session", SESSION_ID);
    const container = document.getElementById("chat-messages");
    container.innerHTML = "";
    // Re-add welcome message
    const welcome = document.createElement("div");
    welcome.className = "flex justify-start items-start gap-3 msg-animate";
    welcome.innerHTML = `
        <div class="w-8 h-8 rounded-full bg-surface-container-highest flex items-center justify-center shrink-0 border border-outline-variant/30">
            <span class="material-symbols-outlined text-xs text-primary">smart_toy</span>
        </div>
        <div class="max-w-[85%] md:max-w-[70%] bg-surface-container-lowest/80 border border-outline-variant/10 px-5 md:px-7 py-4 md:py-5 rounded-2xl rounded-tl-none bot-msg">
            <p class="text-sm md:text-[15px] leading-relaxed">Welcome! I'm <strong>ElectionGuide AI</strong> 🇮🇳</p>
            <p class="text-sm md:text-[15px] leading-relaxed mt-2">I can help you understand India's election process — from voter registration to results declaration. Ask me anything or pick a topic above!</p>
        </div>`;
    container.appendChild(welcome);
}

/* ─── Live Demo ─── */
async function startLiveDemo() {
    // Firebase Analytics — track demo launch
    if (window.firebaseLogEvent) window.firebaseLogEvent("demo_started", { questions: DEMO_QUESTIONS.length });
    const overlay = document.getElementById("demo-overlay");
    const demoChat = document.getElementById("demo-chat");
    const demoProgress = document.getElementById("demo-progress");
    overlay.classList.remove("hidden");
    overlay.classList.add("flex");
    demoChat.innerHTML = "";

    // Build progress dots
    demoProgress.innerHTML = DEMO_QUESTIONS.map((_, i) => `
        <div id="demo-dot-${i}" class="w-2.5 h-2.5 rounded-full bg-outline-variant/30 transition-colors duration-500"></div>
    `).join("");

    for (let i = 0; i < DEMO_QUESTIONS.length; i++) {
        const dot = document.getElementById(`demo-dot-${i}`);
        dot.className = "w-2.5 h-2.5 rounded-full bg-secondary animate-pulse transition-colors duration-500";

        // Show user question
        const userEl = document.createElement("div");
        userEl.className = "flex justify-end msg-animate";
        userEl.innerHTML = `<div class="max-w-[70%] bg-primary-container text-on-primary-container px-5 py-3 rounded-2xl rounded-tr-none shadow-xl">
            <p class="font-body text-sm leading-relaxed">${escapeHtml(DEMO_QUESTIONS[i])}</p>
        </div>`;
        demoChat.appendChild(userEl);
        demoChat.scrollTop = demoChat.scrollHeight;

        // Typing indicator
        const typEl = document.createElement("div");
        typEl.className = "flex justify-start items-start gap-3 msg-animate";
        typEl.innerHTML = `
            <div class="w-8 h-8 rounded-full bg-surface-container-highest flex items-center justify-center shrink-0 border border-outline-variant/30">
                <span class="material-symbols-outlined text-xs text-primary">smart_toy</span>
            </div>
            <div class="bg-surface-container-lowest/80 border border-outline-variant/10 px-6 py-4 rounded-2xl rounded-tl-none flex gap-1.5">
                <span class="w-2 h-2 rounded-full bg-primary typing-dot"></span>
                <span class="w-2 h-2 rounded-full bg-primary typing-dot"></span>
                <span class="w-2 h-2 rounded-full bg-primary typing-dot"></span>
            </div>`;
        demoChat.appendChild(typEl);
        demoChat.scrollTop = demoChat.scrollHeight;

        try {
            const res = await fetch(`${API}/api/demo`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ question: DEMO_QUESTIONS[i], step: i })
            });
            const data = await res.json();
            typEl.remove();

            if (res.status === 429) {
                const errEl = document.createElement("div");
                errEl.className = "flex justify-start items-start gap-3 msg-animate";
                errEl.innerHTML = `
                    <div class="w-8 h-8 rounded-full bg-surface-container-highest flex items-center justify-center shrink-0 border border-outline-variant/30">
                        <span class="material-symbols-outlined text-xs text-primary">smart_toy</span>
                    </div>
                    <div class="bg-surface-container-lowest/80 border border-outline-variant/10 px-5 py-4 rounded-2xl rounded-tl-none">
                        <p class="text-sm text-on-surface-variant">⏳ The AI is processing many requests right now. Demo paused.</p>
                    </div>`;
                demoChat.appendChild(errEl);
                demoChat.scrollTop = demoChat.scrollHeight;
                dot.className = "w-2.5 h-2.5 rounded-full bg-error transition-colors duration-500";
                break; // Stop the demo on rate limit
            }

            let toolBadge = data.tool_used
                ? `<div class="px-2 py-0.5 bg-tertiary-container/30 text-tertiary text-[10px] rounded uppercase font-bold tracking-widest shimmer mb-3 inline-block">🔧 ${escapeHtml(data.tool_used)}</div>`
                : "";

            const botEl = document.createElement("div");
            botEl.className = "flex justify-start items-start gap-3 msg-animate";
            botEl.innerHTML = `
                <div class="w-8 h-8 rounded-full bg-surface-container-highest flex items-center justify-center shrink-0 border border-outline-variant/30">
                    <span class="material-symbols-outlined text-xs text-primary">smart_toy</span>
                </div>
                <div class="max-w-[80%] bg-surface-container-lowest/80 border border-outline-variant/10 px-5 md:px-7 py-4 md:py-5 rounded-2xl rounded-tl-none bot-msg">
                    ${toolBadge}
                    <div class="text-sm leading-relaxed">${renderMarkdown(data.response || "Processing...")}</div>
                </div>`;
            demoChat.appendChild(botEl);
        } catch (err) {
            typEl.remove();
            const errEl = document.createElement("div");
            errEl.className = "flex justify-start items-start gap-3 msg-animate";
            errEl.innerHTML = `
                <div class="w-8 h-8 rounded-full bg-surface-container-highest flex items-center justify-center shrink-0 border border-outline-variant/30">
                    <span class="material-symbols-outlined text-xs text-primary">smart_toy</span>
                </div>
                <div class="bg-surface-container-lowest/80 border border-outline-variant/10 px-5 py-4 rounded-2xl rounded-tl-none">
                    <p class="text-sm text-on-surface-variant">⚠️ Demo step failed — backend may be unavailable.</p>
                </div>`;
            demoChat.appendChild(errEl);
            break; // Stop the demo on error
        }
        demoChat.scrollTop = demoChat.scrollHeight;
        dot.className = "w-2.5 h-2.5 rounded-full bg-tertiary transition-colors duration-500";

        // Pause between questions — longer spacing to avoid rate limits
        if (i < DEMO_QUESTIONS.length - 1) await sleep(5000);
    }
}

function closeDemo() {
    const overlay = document.getElementById("demo-overlay");
    overlay.classList.add("hidden");
    overlay.classList.remove("flex");
}

/* ─── Utilities ─── */
function setBtnState(loading) {
    const btn = document.getElementById("btn-send");
    const input = document.getElementById("chat-input");
    if (loading) {
        btn.disabled = true;
        btn.classList.add("opacity-50");
        input.disabled = true;
    } else {
        btn.disabled = false;
        btn.classList.remove("opacity-50");
        input.disabled = false;
        input.focus();
    }
}

/* Cooldown: disable input for N ms after a rate limit */
function cooldownInput(ms) {
    setBtnState(true);
    updateStatus(`Rate limited — cooling down...`);
    setTimeout(() => {
        setBtnState(false);
        updateStatus("Online");
    }, ms);
}

function updateStatus(txt) {
    const el = document.getElementById("chat-status");
    if (el) el.textContent = txt;
}

function renderMarkdown(text) {
    if (typeof marked !== "undefined") {
        return marked.parse(text || "");
    }
    return (text || "").replace(/\n/g, "<br>");
}

function escapeHtml(text) {
    const d = document.createElement("div");
    d.textContent = text;
    return d.innerHTML;
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

/* Wire Live Demo button in header */
document.addEventListener("DOMContentLoaded", () => {
    const demoBtn = document.getElementById("btn-live-demo");
    if (demoBtn) demoBtn.addEventListener("click", startLiveDemo);
});
