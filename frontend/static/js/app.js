document.addEventListener('DOMContentLoaded', () => {
    // --- Configuration ---
    const POLL_INTERVAL_ACTIVE = 500; // ms
    const POLL_INTERVAL_IDLE = 3000;  // ms

    // --- DOM Elements ---
    const dom = {
        progressBar: document.getElementById('progress-bar'),
        phaseText: document.getElementById('phase-text'),
        percentText: document.getElementById('percent-text'),
        statusMessage: document.getElementById('status-message'),
        lastItemText: document.getElementById('last-item'),
        updateBtn: document.getElementById('update-btn'),
        errorContainer: document.getElementById('error-container'),
        errorBody: document.getElementById('error-body')
    };

    let timerId = null;

    /**
     * Main UI Update Function.
     * Synchronizes the DOM with the backend state snapshot.
     * @param {Object} data - The JSON response from /api/status
     */
    function updateUI(data) {
        // 1. Progress Indicators
        const percent = data.progress.percent;
        dom.progressBar.style.width = `${percent}%`;
        dom.percentText.textContent = `${percent}%`;
        dom.phaseText.textContent = data.phase;

        // 2. Real-time Ticker ("Updated AAPL")
        dom.lastItemText.textContent = data.lastMessage || "";
        dom.lastItemText.className = "last-item"; // Reset class list
        if (data.lastStatus === "success") dom.lastItemText.classList.add("text-success");
        if (data.lastStatus === "error") dom.lastItemText.classList.add("text-error");

        // 3. Button State
        if (data.isRunning) {
            dom.updateBtn.disabled = true;
            dom.updateBtn.textContent = "Updating...";
        } else {
            dom.updateBtn.disabled = false;
            dom.updateBtn.textContent = "Update Now";
        }

        // 4. Status Message Logic
        if (!data.isRunning && data.phase === "Idle") {
            if (data.progress.total > 0 && data.success) {
                // All green
                dom.statusMessage.innerHTML = '<span class="text-success">✅ All updates successful!</span>';
            } else if (data.errors.length > 0) {
                // Finished with errors
                dom.statusMessage.innerHTML = '<span class="text-error">❌ Completed with errors.</span>';
            } else {
                // Initial state
                dom.statusMessage.textContent = "Ready to update.";
            }
        } else {
            // Running state
            dom.statusMessage.textContent = `Processed ${data.progress.current}/${data.progress.total}`;
        }

        // 5. Error Table Rendering
        renderErrors(data.errors);
    }

    /**
     * Renders the error table dynamically.
     * Hides the container if no errors exist.
     */
    function renderErrors(errors) {
        if (!errors || errors.length === 0) {
            dom.errorContainer.classList.add('hidden');
            return;
        }

        dom.errorContainer.classList.remove('hidden');
        dom.errorBody.innerHTML = ''; // Clear existing rows

        errors.forEach(err => {
            const tr = document.createElement('tr');

            // Item Name Column
            const tdName = document.createElement('td');
            tdName.textContent = err.name;
            tdName.style.fontWeight = "600";

            // Error Message Column
            const tdMsg = document.createElement('td');
            tdMsg.textContent = err.message;

            tr.appendChild(tdName);
            tr.appendChild(tdMsg);
            dom.errorBody.appendChild(tr);
        });
    }

    /**
     * Adaptive Polling Loop.
     * Uses setTimeout recursively to adjust frequency based on state.
     */
    async function pollStatus() {
        try {
            const response = await fetch('/api/status');
            const data = await response.json();
            updateUI(data);

            // Adaptive: Fast when running, slow when idle
            const nextInterval = data.isRunning ? POLL_INTERVAL_ACTIVE : POLL_INTERVAL_IDLE;
            timerId = setTimeout(pollStatus, nextInterval);

        } catch (e) {
            console.error("Polling error:", e);
            // On network failure, retry slowly
            timerId = setTimeout(pollStatus, 5000);
        }
    }

    // --- Interaction ---

    dom.updateBtn.addEventListener('click', async () => {
        try {
            dom.updateBtn.disabled = true;
            dom.updateBtn.textContent = "Requesting...";

            const res = await fetch('/api/trigger', { method: 'POST' });
            if (!res.ok) {
                const d = await res.json();
                alert(d.message);
            } else {
                // Success: Cancel pending timer and poll immediately to show "Updating..."
                if (timerId) clearTimeout(timerId);
                pollStatus();
            }
        } catch (e) {
            alert("Failed to reach server.");
            dom.updateBtn.disabled = false;
        }
    });

    // --- Init ---
    pollStatus();
});
