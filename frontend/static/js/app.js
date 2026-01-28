/**
 * Notion Updater & Transaction Tracker Application Logic
 *
 * This file handles the frontend interactivity for two distinct pages:
 * 1. Dashboard Updater (`/updater`): Manages asset price updates via polling.
 * 2. Transaction Tracker (`/`): Manages receipt scanning, data extraction, and Notion entry creation.
 */

document.addEventListener("DOMContentLoaded", () => {
    // Determine current page context based on body ID
    if (document.getElementById("dashboard-view")) {
        new DashboardController().init();
    } else if (document.getElementById("transaction-view")) {
        new TransactionController().init();
    }
});

/**
 * ============================================================================
 * [Page 1] Dashboard Updater Controller
 * ============================================================================
 * Handles the logic for the Financial Dashboard Updater page.
 * Features:
 * - High-frequency polling (500ms) for real-time progress updates.
 * - Displays errors and success messages.
 */
class DashboardController {
    constructor() {
        this.POLL_INTERVAL = 500; // Fast polling for immediate feedback
        this.timerId = null;

        // DOM Elements
        this.dom = {
            progressBar: document.getElementById("progress-bar"),
            phaseText: document.getElementById("phase-text"),
            percentText: document.getElementById("percent-text"),
            statusMessage: document.getElementById("status-message"),
            lastItemText: document.getElementById("last-item"),
            updateBtn: document.getElementById("update-btn"),
            errorContainer: document.getElementById("error-container"),
            errorBody: document.getElementById("error-body"),
        };
    }

    /** Initialize the controller */
    init() {
        this.pollStatus();
        this.setupListeners();
    }

    /** Setup event listeners for user interactions */
    setupListeners() {
        if (this.dom.updateBtn) {
            this.dom.updateBtn.addEventListener("click", () => this.handleUpdateClick());
        }
    }

    /** Handle "Update Now" button click */
    async handleUpdateClick() {
        try {
            this.dom.updateBtn.disabled = true;
            this.dom.updateBtn.textContent = "Requesting...";

            const res = await fetch("/api/trigger", { method: "POST" });
            if (!res.ok) {
                const data = await res.json();
                alert(data.message);
            } else {
                // If a previous timer exists, clear it to start fresh immediately
                if (this.timerId) clearTimeout(this.timerId);
                this.pollStatus();
            }
        } catch (e) {
            alert("Failed to reach server.");
            this.dom.updateBtn.disabled = false;
        }
    }

    /**
     * Polls the backend status API recursively.
     * Uses a fixed interval to keep UI responsive.
     */
    async pollStatus() {
        try {
            const response = await fetch("/api/status");
            const data = await response.json();
            this.updateUI(data);

            // Schedule next poll
            this.timerId = setTimeout(() => this.pollStatus(), this.POLL_INTERVAL);
        } catch (e) {
            console.error("Polling error:", e);
            // Retry with backoff if network fails
            this.timerId = setTimeout(() => this.pollStatus(), 5000);
        }
    }

    /** Updates the DOM based on the current state snapshot */
    updateUI(data) {
        // 1. Progress Indicators
        const percent = data.progress.percent;
        if (this.dom.progressBar) this.dom.progressBar.style.width = `${percent}%`;
        if (this.dom.percentText) this.dom.percentText.textContent = `${percent}%`;
        if (this.dom.phaseText) this.dom.phaseText.textContent = data.phase;

        // 2. Real-time Ticker
        if (this.dom.lastItemText) {
            this.dom.lastItemText.textContent = data.lastMessage || "";
            this.dom.lastItemText.className = "last-item"; // Reset classes
            if (data.lastStatus === "success") this.dom.lastItemText.classList.add("text-success");
            if (data.lastStatus === "error") this.dom.lastItemText.classList.add("text-error");
        }

        // 3. Button State
        if (this.dom.updateBtn) {
            if (data.isRunning) {
                this.dom.updateBtn.disabled = true;
                this.dom.updateBtn.textContent = "Updating...";
            } else {
                this.dom.updateBtn.disabled = false;
                this.dom.updateBtn.textContent = "🔄 Update Now";
            }
        }

        // 4. Status Message Logic
        if (this.dom.statusMessage) {
            if (!data.isRunning && data.phase === "Idle") {
                if (data.progress.total > 0 && data.success) {
                    this.dom.statusMessage.innerHTML = '<span class="text-success">✅ All updates successful!</span>';
                } else if (data.errors.length > 0) {
                    this.dom.statusMessage.innerHTML = '<span class="text-error">❌ Completed with errors.</span>';
                } else {
                    this.dom.statusMessage.textContent = "Ready to update.";
                }
            } else {
                this.dom.statusMessage.textContent = `Processed ${data.progress.current}/${data.progress.total}`;
            }
        }

        // 5. Error Table
        this.renderErrors(data.errors);
    }

    /** Renders the error list if any exist */
    renderErrors(errors) {
        if (!this.dom.errorContainer) return;

        if (!errors || errors.length === 0) {
            this.dom.errorContainer.classList.add("hidden");
            return;
        }

        this.dom.errorContainer.classList.remove("hidden");
        this.dom.errorBody.innerHTML = "";

        errors.forEach((err) => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td style="font-weight: 600;">${err.name}</td>
                <td>${err.message}</td>
            `;
            this.dom.errorBody.appendChild(tr);
        });
    }
}

/**
 * ============================================================================
 * [Page 2] Transaction Tracker Controller
 * ============================================================================
 * Handles logic for the receipt scanner page.
 * Flows: Upload -> Extract (AI) -> Confirm -> Submit (Notion).
 */
class TransactionController {
    constructor() {
        // API Endpoints
        this.API = {
            OPTIONS: "/api/transaction/options",
            UPLOAD: "/api/transaction/upload",
            CONFIRM: "/api/transaction/confirm",
        };

        // Constants
        this.MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
        this.MESSAGES = {
            NO_FILE: "Please upload an image file",
            INVALID_TYPE: "Please upload an image file (JPG, PNG)",
            FILE_TOO_LARGE: "Image size cannot exceed 10MB",
            MISSING_FIELDS: "Please fill in all required fields",
            NETWORK_ERROR: "Network error, please check connection and retry",
            EXTRACTION_FAILED: "Extraction failed, please retry",
            CREATION_FAILED: "Creation failed, please retry",
            ANALYZING: "AI analyzing...",
            SUBMITTING: "Submitting...",
        };

        // DOM Elements
        this.dom = {
            // Panels
            uploadZone: document.getElementById("upload-zone"),
            processing: document.getElementById("processing"),
            results: document.getElementById("results"),
            success: document.getElementById("success"),
            error: document.getElementById("error"),
            mainFooter: document.getElementById("main-footer"),

            // Inputs
            fileInput: document.getElementById("file-input"),
            inputMerchant: document.getElementById("input-merchant"),
            inputAmount: document.getElementById("input-amount"),
            inputCategory: document.getElementById("input-category"),
            inputAccount: document.getElementById("input-account"),
            inputDate: document.getElementById("input-date"),

            // Outputs
            processingText: document.getElementById("processing-text"),
            errorMessage: document.getElementById("error-message"),
            notionLink: document.getElementById("notion-link"),

            // Buttons
            confirmBtn: document.getElementById("confirm-btn"),
            cancelBtn: document.getElementById("cancel"), // Renamed from uploadAnother
            backToHomeBtn: document.getElementById("back-to-home"), // Renamed from uploadNew
            retryBtn: document.getElementById("retry-btn"),
        };

        // State
        this.currentFile = null;
        this.categories = [];
        this.accounts = [];
    }

    /** Initialize the controller */
    init() {
        this.fetchOptions();
        this.setupUploadListeners();
        this.setupActionListeners();
    }

    /** Fetch Categories and Accounts from backend */
    async fetchOptions() {
        try {
            const response = await fetch(this.API.OPTIONS);
            const result = await response.json();
            if (result.success) {
                this.categories = result.categories || [];
                this.accounts = result.accounts || [];
                this.populateSelects();
            }
        } catch (error) {
            console.error("Failed to fetch options:", error);
        }
    }

    /** Setup Drag & Drop and File Input listeners */
    setupUploadListeners() {
        if (!this.dom.uploadZone) return;

        // Click to open file dialog
        this.dom.uploadZone.addEventListener("click", () => this.dom.fileInput.click());

        // Handle file selection
        this.dom.fileInput.addEventListener("change", (e) => {
            const file = e.target.files[0];
            if (file) this.handleFile(file);
        });

        // Drag & Drop visual feedback
        this.dom.uploadZone.addEventListener("dragover", (e) => {
            e.preventDefault();
            this.dom.uploadZone.classList.add("dragover");
        });
        this.dom.uploadZone.addEventListener("dragleave", () => {
            this.dom.uploadZone.classList.remove("dragover");
        });
        this.dom.uploadZone.addEventListener("drop", (e) => {
            e.preventDefault();
            this.dom.uploadZone.classList.remove("dragover");
            const file = e.dataTransfer.files[0];
            if (file) this.handleFile(file);
        });
    }

    /** Setup Button actions */
    setupActionListeners() {
        if (this.dom.confirmBtn) {
            this.dom.confirmBtn.addEventListener("click", () => this.handleConfirm());
        }
        if (this.dom.cancelBtn) {
            this.dom.cancelBtn.addEventListener("click", () => this.resetUI());
        }
        if (this.dom.backToHomeBtn) {
            this.dom.backToHomeBtn.addEventListener("click", () => this.resetUI());
        }
        if (this.dom.retryBtn) {
            this.dom.retryBtn.addEventListener("click", () => {
                if (this.currentFile) this.handleFile(this.currentFile);
                else this.resetUI();
            });
        }
    }

    /** Handle file upload and AI extraction */
    async handleFile(file) {
        this.currentFile = file;

        // Validation
        if (!file.type.startsWith("image/")) return this.showError(this.MESSAGES.INVALID_TYPE);
        if (file.size > this.MAX_FILE_SIZE) return this.showError(this.MESSAGES.FILE_TOO_LARGE);

        this.showProcessing(this.MESSAGES.ANALYZING);

        try {
            const formData = new FormData();
            formData.append("file", file);

            const response = await fetch(this.API.UPLOAD, {
                method: "POST",
                body: formData,
            });

            const result = await response.json();
            if (result.success) {
                this.showEditableResults(result.data);
            } else {
                this.showError(result.error || this.MESSAGES.EXTRACTION_FAILED);
            }
        } catch (error) {
            console.error("Upload error:", error);
            this.showError(this.MESSAGES.NETWORK_ERROR);
        }
    }

    /** Handle final confirmation and submission to Notion */
    async handleConfirm() {
        const data = {
            merchant: this.dom.inputMerchant.value,
            amount: parseFloat(this.dom.inputAmount.value),
            category: this.dom.inputCategory.value,
            account: this.dom.inputAccount.value,
            date: this.dom.inputDate.value,
        };

        if (!data.merchant || !data.amount || !data.category || !data.account) {
            this.showError(this.MESSAGES.MISSING_FIELDS);
            return;
        }

        this.showProcessing(this.MESSAGES.SUBMITTING);

        try {
            const response = await fetch(this.API.CONFIRM, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(data),
            });

            const result = await response.json();
            if (result.success) {
                this.showSuccess(result.notionUrl);
            } else {
                this.showError(result.error || this.MESSAGES.CREATION_FAILED);
            }
        } catch (error) {
            console.error("Confirm error:", error);
            this.showError(this.MESSAGES.NETWORK_ERROR);
        }
    }

    // --- UI Helper Methods ---

    populateSelects() {
        if (!this.dom.inputCategory || !this.dom.inputAccount) return;

        this.dom.inputCategory.innerHTML = '<option value="">Select category</option>';
        this.dom.inputAccount.innerHTML = '<option value="">Select account</option>';

        this.categories.forEach((name) => {
            const opt = document.createElement("option");
            opt.value = name;
            opt.textContent = name;
            this.dom.inputCategory.appendChild(opt);
        });

        this.accounts.forEach((name) => {
            const opt = document.createElement("option");
            opt.value = name;
            opt.textContent = name;
            this.dom.inputAccount.appendChild(opt);
        });
    }

    showProcessing(message) {
        this.hideAllViews();
        if (this.dom.processing) this.dom.processing.classList.remove("hidden");
        if (this.dom.processingText) this.dom.processingText.textContent = message;
    }

    showEditableResults(data) {
        this.hideAllViews();
        if (this.dom.results) this.dom.results.classList.remove("hidden");

        if (this.dom.inputMerchant) this.dom.inputMerchant.value = data.merchant || "";
        if (this.dom.inputAmount) this.dom.inputAmount.value = data.amount || "";
        if (this.dom.inputCategory) this.dom.inputCategory.value = data.category || "";
        if (this.dom.inputAccount) this.dom.inputAccount.value = data.account || "";
        if (this.dom.inputDate) this.dom.inputDate.value = data.date || "";
    }

    showSuccess(notionUrl) {
        this.hideAllViews();
        if (this.dom.success) this.dom.success.classList.remove("hidden");
        if (this.dom.notionLink) this.dom.notionLink.href = notionUrl;
    }

    showError(message) {
        this.hideAllViews();
        if (this.dom.error) this.dom.error.classList.remove("hidden");
        if (this.dom.errorMessage) this.dom.errorMessage.textContent = message;
    }

    resetUI() {
        this.currentFile = null;
        if (this.dom.fileInput) this.dom.fileInput.value = "";
        this.hideAllViews();
        if (this.dom.uploadZone) this.dom.uploadZone.classList.remove("hidden");

        // Restore main footer when returning to start page
        if (this.dom.mainFooter) this.dom.mainFooter.classList.remove("hidden");
    }

    hideAllViews() {
        const views = [
            this.dom.uploadZone,
            this.dom.processing,
            this.dom.results,
            this.dom.success,
            this.dom.error,
            this.dom.mainFooter, // Hide footer in non-home views
        ];
        views.forEach((el) => {
            if (el) el.classList.add("hidden");
        });
    }
}
