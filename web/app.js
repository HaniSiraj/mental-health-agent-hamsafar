/* ==============================================================================
   HAMSAFAR DYNAMIC CORE JS - CHAT ENGINE & 3D BREATHING ORB (THREE.JS)
   ============================================================================== */

// Generate or load a persistent Session ID
let sessionId = localStorage.getItem("hamsafar_session_id");
if (!sessionId) {
    sessionId = "HAMS-" + Math.random().toString(36).substring(2, 8).toUpperCase();
    localStorage.setItem("hamsafar_session_id", sessionId);
}

// 3D Orb Interactive State
let activeExercise = "breathing";
let currentOrbColor = null;
let targetOrbColor = null;

// UI Elements
const chatMessages = document.getElementById("chat-messages");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const resetSessionBtn = document.getElementById("reset-session-btn");
const sessionIdDisplay = document.getElementById("session-id-display");
const consentMoodCheckbox = document.getElementById("consent-mood-checkbox");
const toggleOrbCheckbox = document.getElementById("toggle-orb-checkbox");
let orbEnabled = true;

// Load initial orb preference
const savedOrbPref = localStorage.getItem("hamsafar_orb_enabled");
orbEnabled = savedOrbPref === null ? true : savedOrbPref === "true";

// Telemetry Elements
const noTracePlaceholder = document.getElementById("no-trace-placeholder");
const traceDisplay = document.getElementById("trace-display");

const traceNormalizerLang = document.getElementById("trace-normalizer-lang");
const traceNormalizerOriginal = document.getElementById("trace-normalizer-original");
const traceNormalizerOutput = document.getElementById("trace-normalizer-output");

const traceSafetyTier = document.getElementById("trace-safety-tier");
const traceSafetyReasoning = document.getElementById("trace-safety-reasoning");
const traceSafetySignals = document.getElementById("trace-safety-signals");

const cardCbtState = document.getElementById("card-cbt-state");
const traceCbtStep = document.getElementById("trace-cbt-step");
const cbtStepsContainer = document.getElementById("cbt-steps-container");

const traceSupervisorIntent = document.getElementById("trace-supervisor-intent");
const traceSupervisorReasoning = document.getElementById("trace-supervisor-reasoning");
const traceSupervisorRoutes = document.getElementById("trace-supervisor-routes");

const traceSynthesisLength = document.getElementById("trace-synthesis-length");
const breathingStatusText = document.getElementById("breathing-status");

const API_BASE = "";

// ----------------------------------------------------------------------------
// INITIALIZATION
// ----------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", async () => {
    sessionIdDisplay.textContent = sessionId;
    
    // Initialize 3D Breathing Orb scene
    initThreeJSScene();
    updateOrbVisibility();
    
    // Sync session from Redis
    await syncSessionProfile();
    
    // Welcome Greeting
    addMessage("assistant", 
        "Assalam-o-Alaikum! I am Hamsafar, your companion. " +
        "I am here to guide you through stateful cognitive exercises, share calming perspectives, " +
        "and provide a supportive safe space. You can chat in English or Roman Urdu.<br><br>" +
        "Try matching your breaths with the **3D Breathing Orb** floating in the background."
    );
});

async function syncSessionProfile() {
    try {
        const response = await fetch(`${API_BASE}/api/session/${sessionId}`);
        if (response.ok) {
            const data = await response.json();
            
            // Sync active exercise state
            if (data.active_protocol) {
                activeExercise = data.active_protocol.name;
            } else {
                activeExercise = "breathing";
            }
            
            // Sync Consent
            const consent = data.consent || { memory: true, mood_logging: false };
            consentMoodCheckbox.checked = consent.mood_logging;
            
            // Render logs if present
            const turns = data.turns || [];
            if (turns.length > 0) {
                chatMessages.innerHTML = "";
                turns.forEach(turn => {
                    let content = turn.content;
                    if (turn.role === "assistant" && content.includes("---")) {
                        content = content.split("---")[0].trim();
                    }
                    addMessage(turn.role, content, false);
                });
            }
        }
    } catch (e) {
        console.warn("Failed to load historical profile: ", e);
    }
}

// ----------------------------------------------------------------------------
// CONSENT & ORB TOGGLE CONFIGS
// ----------------------------------------------------------------------------

if (toggleOrbCheckbox) {
    toggleOrbCheckbox.checked = orbEnabled;
    toggleOrbCheckbox.addEventListener("change", () => {
        orbEnabled = toggleOrbCheckbox.checked;
        localStorage.setItem("hamsafar_orb_enabled", orbEnabled);
        updateOrbVisibility();
    });
}

function updateOrbVisibility() {
    const container = document.getElementById("three-container");
    if (!container) return;
    if (orbEnabled) {
        container.classList.remove("hidden");
    } else {
        container.classList.add("hidden");
    }
}

consentMoodCheckbox.addEventListener("change", async () => {
    try {
        const payload = {
            memory: true,
            mood_logging: consentMoodCheckbox.checked
        };
        await fetch(`${API_BASE}/api/consent/${sessionId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        
        const status = consentMoodCheckbox.checked ? "enabled" : "disabled";
        addMessage("assistant", `I have updated your profile. Mood Synchronization is now ${status}.`);
    } catch (e) {
        console.error("Failed to update consent:", e);
    }
});

// ----------------------------------------------------------------------------
// CHAT MESSAGES
// ----------------------------------------------------------------------------

chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = chatInput.value.trim();
    if (!text) return;
    
    addMessage("user", text);
    chatInput.value = "";
    
    const loaderId = addTypingLoader();
    
    try {
        const response = await fetch(`${API_BASE}/api/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: sessionId, message: text })
        });
        
        removeTypingLoader(loaderId);
        
        if (response.ok) {
            const data = await response.json();
            const cleanReply = data.reply.replace(/\n/g, "<br>");
            addMessage("assistant", cleanReply);
            
            updateTelemetry(data.cognitive_trace);
        } else {
            addMessage("assistant", "I had an issue connecting to my cognitive system.");
        }
    } catch (err) {
        removeTypingLoader(loaderId);
        addMessage("assistant", "Unable to establish network connection. Check that FastAPI is running.");
    }
});

function triggerCBTPill(protocolText) {
    chatInput.value = `Let's start the ${protocolText} exercise.`;
    chatForm.dispatchEvent(new Event("submit"));
}

function addMessage(role, text, scroll = true) {
    const bubble = document.createElement("div");
    bubble.classList.add("message", role);
    
    let formattedText = text.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    
    if (role === "assistant" && formattedText.includes("---")) {
        const parts = formattedText.split("---");
        formattedText = parts[0] + "<hr><p class='disclaimer'>" + parts[1].replace("*", "") + "</p>";
    }
    
    bubble.innerHTML = formattedText;
    chatMessages.appendChild(bubble);
    
    if (scroll) {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
}

function addTypingLoader() {
    const id = "loader-" + Date.now();
    const bubble = document.createElement("div");
    bubble.classList.add("message", "assistant", "typing-bubble");
    bubble.setAttribute("id", id);
    
    bubble.innerHTML = `
        <div class="typing-indicator">
            <span></span>
            <span></span>
            <span></span>
        </div>
    `;
    chatMessages.appendChild(bubble);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return id;
}

function removeTypingLoader(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

resetSessionBtn.addEventListener("click", async () => {
    if (confirm("Reset current session and clear state?")) {
        try {
            await fetch(`${API_BASE}/api/reset/${sessionId}`, { method: "POST" });
            localStorage.removeItem("hamsafar_session_id");
            window.location.reload();
        } catch (e) {
            window.location.reload();
        }
    }
});

// ----------------------------------------------------------------------------
// COGNITIVE TELEMETRY PANEL
// ----------------------------------------------------------------------------

function updateTelemetry(trace) {
    if (!trace || trace.status === "failed" || trace.error) {
        console.error("Hamsafar Pipeline Error Trace:", trace);
        return;
    }
    
    // Update active exercise state for 3D orb behavior
    const safety = trace.safety || {};
    const tier = safety.tier || 3;
    const routing = trace.routing || {};
    const cbtOverride = routing.active_cbt_override || false;
    
    if (tier === 1 || tier === 2) {
        activeExercise = "crisis";
    } else if (cbtOverride) {
        activeExercise = routing.cbt_protocol || "thought_record";
    } else {
        activeExercise = "breathing";
    }
    
    noTracePlaceholder.classList.add("hidden");
    traceDisplay.classList.remove("hidden");
    
    const norm = trace.normalization || {};
    traceNormalizerLang.textContent = (norm.detected_lang || "EN").replace("_", " ");
    traceNormalizerOriginal.textContent = trace.input_message;
    traceNormalizerOutput.textContent = norm.normalized_text || trace.input_message;
    
    traceSafetyTier.textContent = `Tier ${tier}`;
    traceSafetyReasoning.textContent = safety.reasoning || "Passed safety assessment.";
    
    const safetyCard = document.getElementById("card-safety");
    safetyCard.className = "telemetry-card";
    
    const safetyPill = document.getElementById("trace-safety-tier");
    safetyPill.className = "tech-tag";
    
    if (tier === 1 || tier === 2) {
        safetyPill.classList.add("tag-red");
        safetyCard.classList.add("border-danger");
    } else {
        safetyPill.classList.add("tag-cyan");
    }
    
    traceSafetySignals.innerHTML = "";
    const signals = safety.signals || [];
    if (signals.length === 0) {
        traceSafetySignals.innerHTML = "<span class='sig-tag'>None</span>";
    } else {
        signals.forEach(sig => {
            const span = document.createElement("span");
            span.classList.add("sig-tag");
            if (tier === 1 || tier === 2) span.classList.add("sig-tag-crisis");
            span.textContent = sig;
            traceSafetySignals.appendChild(span);
        });
    }
    
    if (cbtOverride) {
        cardCbtState.classList.remove("hidden");
        document.getElementById("card-supervisor").classList.add("hidden");
        
        const pName = routing.cbt_protocol || "thought_record";
        const stateStr = routing.current_state || "step_0_of_6";
        
        const currStep = parseInt(stateStr.split("_")[1]);
        const totalSteps = parseInt(stateStr.split("_")[3]) || 6;
        
        traceCbtStep.textContent = `${pName.replace("_", " ").toUpperCase()}: ${currStep + 1}/${totalSteps}`;
        
        let labels = ["Trigger", "Emotion", "Hot Thought", "Evidence", "Reframe", "Outcome"];
        if (pName === "worry_postponement") {
            labels = ["Worry", "Schedule"];
        } else if (pName === "activity_scheduling") {
            labels = ["Ideas", "Schedule", "Difficulty", "Logged"];
        }
        
        cbtStepsContainer.innerHTML = "";
        for (let i = 0; i < totalSteps; i++) {
            const node = document.createElement("div");
            node.classList.add("cbt-step-node");
            node.textContent = i + 1;
            
            if (i < currStep) {
                node.classList.add("completed");
            } else if (i === currStep) {
                node.classList.add("active");
            }
            
            const stepLabel = document.createElement("span");
            stepLabel.classList.add("cbt-step-label");
            stepLabel.textContent = labels[i] || `S${i+1}`;
            node.appendChild(stepLabel);
            cbtStepsContainer.appendChild(node);
        }
    } else {
        cardCbtState.classList.add("hidden");
        document.getElementById("card-supervisor").classList.remove("hidden");
        
        traceSupervisorIntent.textContent = routing.user_intent || "Evaluate";
        traceSupervisorReasoning.textContent = routing.reasoning || "Analyzing message intent and routing.";
        
        traceSupervisorRoutes.innerHTML = "";
        const routedAgents = routing.agents || ["reflection"];
        routedAgents.forEach(agent => {
            const badge = document.createElement("div");
            badge.classList.add("route-agent-badge");
            badge.innerHTML = `<i class="fa-solid fa-circle-check"></i> ${agent.toUpperCase()}`;
            traceSupervisorRoutes.appendChild(badge);
        });
    }
    
    const synth = trace.synthesis || {};
    traceSynthesisLength.textContent = `${synth.response_length_chars || 0} chars`;
}

// ----------------------------------------------------------------------------
// THREE.JS: CALMING BREATHING ORB (WEBGL SCENE)
// ----------------------------------------------------------------------------

let scene, camera, renderer, clock;
let solidOrb, wireOrb, orbGroup;
let originalPositions = [];

function initThreeJSScene() {
    const container = document.getElementById("three-container");
    if (!container) return;

    try {
    // 1. Scene & Setup
    currentOrbColor = new THREE.Color(0x22d3ee);
    targetOrbColor = new THREE.Color(0x22d3ee);
    scene = new THREE.Scene();
    clock = new THREE.Clock();

    // 2. Camera
    camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.1, 100);
    camera.position.z = 5;

    // 3. WebGL Renderer
    renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    // 4. Orb Group Creation
    orbGroup = new THREE.Group();

    // Create many-segmented Sphere (made smaller: 1.0 instead of 1.6)
    const geometry = new THREE.SphereGeometry(1.0, 64, 64);
    
    // Save original vertex positions for morphing offset
    const posAttr = geometry.attributes.position;
    for (let i = 0; i < posAttr.count; i++) {
        originalPositions.push(new THREE.Vector3(
            posAttr.getX(i),
            posAttr.getY(i),
            posAttr.getZ(i)
        ));
    }

    // Material 1: Glowing Emissive Core (MeshStandardMaterial — r128 compatible)
    const solidMaterial = new THREE.MeshStandardMaterial({
        color: 0x0a1628,
        emissive: 0x22d3ee,
        emissiveIntensity: 0.8,
        opacity: 0.85,
        transparent: true,
        roughness: 0.2,
        metalness: 0.9,
    });
    solidOrb = new THREE.Mesh(geometry, solidMaterial);
    orbGroup.add(solidOrb);

    // Material 2: Glowing Wireframe Outer Shell
    const wireMaterial = new THREE.MeshBasicMaterial({
        color: 0x22d3ee,
        wireframe: true,
        transparent: true,
        opacity: 0.35
    });
    wireOrb = new THREE.Mesh(geometry.clone(), wireMaterial);
    wireOrb.scale.set(1.02, 1.02, 1.02); // Slightly larger than the core
    orbGroup.add(wireOrb);

    // Material 3: Outer Glow Halo (made smaller: 1.8 instead of 2.8)
    const glowMaterial = new THREE.MeshBasicMaterial({
        color: 0x22d3ee,
        transparent: true,
        opacity: 0.06,
        side: THREE.BackSide
    });
    const glowSphere = new THREE.Mesh(
        new THREE.SphereGeometry(1.8, 32, 32),
        glowMaterial
    );
    orbGroup.add(glowSphere);

    scene.add(orbGroup);

    // 5. Lighting — boosted for visibility
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.15);
    scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0x22d3ee, 2.0); // Strong Cyan
    dirLight1.position.set(5, 5, 3);
    scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0x8b5cf6, 1.5); // Strong Purple
    dirLight2.position.set(-5, -3, 2);
    scene.add(dirLight2);

    const pointLight = new THREE.PointLight(0x22d3ee, 1.5, 15); // Close-range glow
    pointLight.position.set(0, 0, 3);
    scene.add(pointLight);

    // Resize Handler
    window.addEventListener("resize", onWindowResize);

    // Start Animate Loop
    animate();
    console.log("Hamsafar 3D Breathing Orb initialized successfully.");

    } catch (err) {
        console.error("Failed to initialize 3D Breathing Orb:", err);
    }
}

function onWindowResize() {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
}

function animate() {
    requestAnimationFrame(animate);

    // Skip updates and rendering if disabled to conserve CPU/GPU
    if (!orbEnabled) return;

    const time = clock.getElapsedTime();

    // 1. Morph Orb Vertices using waves (Organic deformation)
    if (solidOrb && originalPositions.length > 0) {
        const posAttr = solidOrb.geometry.attributes.position;
        const vertex = new THREE.Vector3();
        
        for (let i = 0; i < posAttr.count; i++) {
            vertex.copy(originalPositions[i]);
            const wave = Math.sin(vertex.x * 1.5 + time) * 
                         Math.cos(vertex.y * 1.5 + time) * 
                         Math.sin(vertex.z * 1.5 + time);
            const normal = vertex.clone().normalize();
            vertex.add(normal.multiplyScalar(wave * 0.16));
            posAttr.setXYZ(i, vertex.x, vertex.y, vertex.z);
        }
        posAttr.needsUpdate = true;

        const wirePosAttr = wireOrb.geometry.attributes.position;
        for (let i = 0; i < wirePosAttr.count; i++) {
            vertex.copy(originalPositions[i]);
            const wave = Math.sin(vertex.x * 1.5 + (time - 0.2)) * 
                         Math.cos(vertex.y * 1.5 + (time - 0.2)) * 
                         Math.sin(vertex.z * 1.5 + (time - 0.2));
            const normal = vertex.clone().normalize();
            vertex.add(normal.multiplyScalar(wave * 0.16));
            wirePosAttr.setXYZ(i, vertex.x, vertex.y, vertex.z);
        }
        wirePosAttr.needsUpdate = true;
    }

    // 2. Slow Rotations
    orbGroup.rotation.y = time * 0.08;
    orbGroup.rotation.x = time * 0.05;

    // 3. Dynamic exercise styling (colors and breathing cycles)
    let cycleTime = 8.0; // Default: 8s breathing
    let colorHex = 0x22d3ee; // Default: Calming Cyan
    
    if (activeExercise === "crisis") {
        cycleTime = 16.0; // Box Breathing
        colorHex = 0x10b981; // Calming Emerald Green
    } else if (activeExercise === "thought_record") {
        cycleTime = 10.0;
        colorHex = 0x8b5cf6; // Focused Deep Purple
    } else if (activeExercise === "worry_postponement") {
        cycleTime = 12.0;
        colorHex = 0xf59e0b; // Centering Amber/Orange
    } else if (activeExercise === "activity_scheduling") {
        cycleTime = 6.0;
        colorHex = 0x0ea5e9; // Energizing Light Blue
    }
    
    targetOrbColor.setHex(colorHex);
    currentOrbColor.lerp(targetOrbColor, 0.05); // Smoothly transition colors

    // Apply color to materials
    if (solidOrb && solidOrb.material) {
        solidOrb.material.emissive.copy(currentOrbColor);
    }
    if (wireOrb && wireOrb.material) {
        wireOrb.material.color.copy(currentOrbColor);
    }

    // Calculate scaling and texts in sync
    const breathPeriod = time % cycleTime;
    let breathScale = 1.0;
    let glowIntensity = 0.2;
    
    if (activeExercise === "crisis") {
        // Box Breathing: 4s inhale, 4s hold, 4s exhale, 4s hold
        if (breathPeriod < 4.0) {
            // Inhale
            const progress = breathPeriod / 4.0;
            breathScale = 1.0 + progress * 0.18;
            glowIntensity = 0.3 + progress * 0.5;
            if (breathingStatusText) breathingStatusText.textContent = "Inhale (4s)...";
        } else if (breathPeriod < 8.0) {
            // Hold
            breathScale = 1.18;
            glowIntensity = 0.8;
            if (breathingStatusText) breathingStatusText.textContent = "Hold Breath (4s)...";
        } else if (breathPeriod < 12.0) {
            // Exhale
            const progress = (breathPeriod - 8.0) / 4.0;
            breathScale = 1.18 - progress * 0.18;
            glowIntensity = 0.8 - progress * 0.5;
            if (breathingStatusText) breathingStatusText.textContent = "Exhale (4s)...";
        } else {
            // Rest/Hold
            breathScale = 1.0;
            glowIntensity = 0.3;
            if (breathingStatusText) breathingStatusText.textContent = "Rest (4s)...";
        }
    } else {
        // Standard Inhale/Exhale split (50/50 of cycleTime)
        const halfCycle = cycleTime / 2.0;
        if (breathPeriod < halfCycle) {
            const progress = breathPeriod / halfCycle;
            breathScale = 1.0 + progress * 0.18;
            glowIntensity = 0.3 + progress * 0.6;
            
            if (activeExercise === "thought_record") {
                if (breathingStatusText) breathingStatusText.textContent = "Focus Inward...";
            } else if (activeExercise === "worry_postponement") {
                if (breathingStatusText) breathingStatusText.textContent = "Gather Calm...";
            } else if (activeExercise === "activity_scheduling") {
                if (breathingStatusText) breathingStatusText.textContent = "Absorb Energy...";
            } else {
                if (breathingStatusText) breathingStatusText.textContent = "Inhale Slowly...";
            }
        } else {
            const progress = (breathPeriod - halfCycle) / halfCycle;
            breathScale = 1.18 - progress * 0.18;
            glowIntensity = 0.9 - progress * 0.6;
            
            if (activeExercise === "thought_record") {
                if (breathingStatusText) breathingStatusText.textContent = "Release Tension...";
            } else if (activeExercise === "worry_postponement") {
                if (breathingStatusText) breathingStatusText.textContent = "Let Go of Worries...";
            } else if (activeExercise === "activity_scheduling") {
                if (breathingStatusText) breathingStatusText.textContent = "Activate Mind...";
            } else {
                if (breathingStatusText) breathingStatusText.textContent = "Exhale Gently...";
            }
        }
    }

    orbGroup.scale.set(breathScale, breathScale, breathScale);

    if (solidOrb && solidOrb.material) {
        solidOrb.material.emissiveIntensity = glowIntensity;
    }
    if (wireOrb && wireOrb.material) {
        wireOrb.material.opacity = 0.12 + glowIntensity * 0.25;
    }

    // 4. Render
    renderer.render(scene, camera);
}
