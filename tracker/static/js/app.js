/**
 * Notion Transaction Tracker Application Logic
 *
 * Handles receipt scanning, data extraction, and Notion entry creation.
 */

document.addEventListener("DOMContentLoaded", () => {
    if (document.getElementById("transaction-view")) {
        new TransactionController().init();
    }
});

/**
 * ============================================================================
 * Transaction Tracker Controller
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
            MISSING_FIELDS: "Please fill in amount and date",
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

    /** Fetch Categories and Accounts */
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

        if (!data.amount || !data.date) {
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

    }

    hideAllViews() {
        const views = [
            this.dom.uploadZone,
            this.dom.processing,
            this.dom.results,
            this.dom.success,
            this.dom.error,
        ];
        views.forEach((el) => {
            if (el) el.classList.add("hidden");
        });
    }
}
