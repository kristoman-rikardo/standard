/**
 * StandardGPT - Modern JavaScript Application
 * Handles user interactions, API calls, and UI updates
 */

class StandardGPTApp {
    constructor() {
        this.currentRequest = null;
        this.isLoading = false;
        this.debugVisible = true;
        this.sessionId = this.getOrCreateSessionId();
        
        // DOM Elements
        this.elements = {
            questionInput: document.getElementById('questionInput'),
            submitBtn: document.getElementById('submitBtn'),
            clearBtn: document.getElementById('clearBtn'),
            loadingContainer: document.getElementById('loadingContainer'),
            resultsContainer: document.getElementById('resultsContainer'),
            answerContent: document.getElementById('answerContent'),
            debugContent: document.getElementById('debugContent'),
            debugToggle: document.getElementById('debugToggle'),
            processingTime: document.getElementById('processingTime'),
            securityStatus: document.getElementById('securityStatus'),
            examplesContainer: document.getElementById('examplesContainer'),
            cancelBtn: document.getElementById('cancelBtn')
        };
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.loadExamples();
        this.setupKeyboardShortcuts();
        this.setupAccessibility();
        
        // Focus input on load
        this.focusInput();
        
        console.log('StandardGPT initialized successfully');
    }
    
    setupEventListeners() {
        // Submit button
        this.elements.submitBtn.addEventListener('click', () => this.submitQuestion());
        
        // Clear button
        this.elements.clearBtn.addEventListener('click', () => this.clearAll());
        
        // Enter key in textarea (Ctrl+Enter to submit)
        this.elements.questionInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && e.ctrlKey) {
                e.preventDefault();
                this.submitQuestion();
            }
        });
        
        // Input validation
        this.elements.questionInput.addEventListener('input', () => this.validateInput());
        
        // Debug toggle
        this.elements.debugToggle.addEventListener('click', () => this.toggleDebug());
        
        // Cancel request
        this.elements.cancelBtn.addEventListener('click', () => this.cancelRequest());
        
        // Auto-resize textarea
        this.elements.questionInput.addEventListener('input', this.autoResizeTextarea.bind(this));
    }
    
    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ctrl+K to focus input
            if (e.ctrlKey && e.key === 'k') {
                e.preventDefault();
                this.focusInput();
            }
            
            // Escape to cancel request or clear
            if (e.key === 'Escape') {
                if (this.isLoading) {
                    this.cancelRequest();
                } else {
                    this.clearAll();
                }
            }
        });
    }
    
    setupAccessibility() {
        // Announce loading state changes
        this.elements.loadingContainer.setAttribute('aria-live', 'polite');
        this.elements.resultsContainer.setAttribute('aria-live', 'polite');
    }
    
    loadExamples() {
        const examples = [
            {
                question: "Hva sier NS-EN ISO 14155 om temperaturkrav?",
                category: "Temperatur"
            },
            {
                question: "Hvilke sikkerhetskrav gjelder for elektriske installasjoner?",
                category: "Sikkerhet"
            },
            {
                question: "Hva er kravene til brannsikkerhet i bygninger?",
                category: "Brann"
            },
            {
                question: "Hvilke standarder gjelder for vannkvalitet?",
                category: "Vann"
            },
            {
                question: "Hva sier standardene om støynivå i arbeidsområder?",
                category: "Støy"
            },
            {
                question: "Hvilke krav stilles til ventilasjon i kontorbygg?",
                category: "Ventilasjon"
            }
        ];
        
        this.elements.examplesContainer.innerHTML = examples.map(example => `
            <div class="example-card" onclick="app.useExample('${example.question.replace(/'/g, "\\'")}')">
                <div class="example-category">${example.category}</div>
                <div class="example-text">${example.question}</div>
            </div>
        `).join('');
    }
    
    useExample(question) {
        this.elements.questionInput.value = question;
        this.validateInput();
        this.focusInput();
        
        // Smooth scroll to input
        this.elements.questionInput.scrollIntoView({ 
            behavior: 'smooth', 
            block: 'center' 
        });
    }
    
    validateInput() {
        const question = this.elements.questionInput.value.trim();
        const isValid = question.length >= 3 && question.length <= 1000;
        
        this.elements.submitBtn.disabled = !isValid || this.isLoading;
        
        // Update character count
        const helpText = document.querySelector('.help-text');
        if (helpText) {
            const remaining = 1000 - question.length;
            helpText.textContent = `${question.length}/1000 tegn (${remaining} igjen)`;
            
            if (remaining < 50) {
                helpText.classList.add('warning');
            } else {
                helpText.classList.remove('warning');
            }
        }
        
        return isValid;
    }
    
    autoResizeTextarea() {
        const textarea = this.elements.questionInput;
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
    }
    
    async submitQuestion() {
        if (!this.validateInput() || this.isLoading) {
            return;
        }
        
        const question = this.elements.questionInput.value.trim();
        
        try {
            this.setLoadingState(true);
            this.hideResults();
            
            const startTime = Date.now();
            
            // Create AbortController for request cancellation
            const controller = new AbortController();
            this.currentRequest = controller;
            
            const response = await fetch('/api/query', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Session-ID': this.sessionId
                },
                body: JSON.stringify({ question }),
                signal: controller.signal
            });
            
            const endTime = Date.now();
            const processingTime = endTime - startTime;
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP ${response.status}`);
            }
            
            const data = await response.json();
            
            this.displayResults(data, processingTime);
            
        } catch (error) {
            if (error.name === 'AbortError') {
                console.log('Request was cancelled');
                return;
            }
            
            this.displayError(error.message);
            console.error('Error submitting question:', error);
        } finally {
            this.setLoadingState(false);
            this.currentRequest = null;
        }
    }
    
    cancelRequest() {
        if (this.currentRequest) {
            this.currentRequest.abort();
            this.currentRequest = null;
        }
        this.setLoadingState(false);
    }
    
    setLoadingState(loading) {
        this.isLoading = loading;
        
        // Update UI elements
        this.elements.submitBtn.disabled = loading;
        this.elements.questionInput.disabled = loading;
        
        if (loading) {
            this.elements.loadingContainer.style.display = 'block';
            this.elements.submitBtn.innerHTML = '⏳ Søker...';
        } else {
            this.elements.loadingContainer.style.display = 'none';
            this.elements.submitBtn.innerHTML = '🚀 Spør StandardGPT';
        }
        
        this.validateInput();
    }
    
    displayResults(data, processingTime) {
        // Update answer content
        this.elements.answerContent.innerHTML = this.formatAnswer(data.answer);
        
        // Update comprehensive debug content with flow visualization
        if (data.flow_debug) {
            this.elements.debugContent.innerHTML = this.formatFlowDebug(data.flow_debug, data.debug);
        } else {
            this.elements.debugContent.textContent = JSON.stringify(data.debug, null, 2);
        }
        
        // Update status information
        this.elements.processingTime.textContent = `${processingTime}ms`;
        this.elements.securityStatus.innerHTML = data.security_sanitized ? 
            '<span class="status-secure">✅ Input sanitized</span>' : 
            '<span class="status-clean">✅ Clean input</span>';
        
        // Show results
        this.showResults();
        
        // Scroll to results
        this.elements.resultsContainer.scrollIntoView({ 
            behavior: 'smooth', 
            block: 'start' 
        });
        
        // Announce to screen readers
        this.announceToScreenReader('Søkeresultater er klare');
    }
    
    formatFlowDebug(flowDebug, generalDebug) {
        return `
            <div class="debug-flow">
                <h4>📊 FlowManager Debug - Komplett Flytoversikt</h4>
                
                <div class="debug-section">
                    <h5>🔄 1. ROUTING BESLUTNING</h5>
                    <div class="debug-item">
                        <strong>Rute valgt:</strong> <span class="route-${flowDebug.route}">${flowDebug.route}</span>
                    </div>
                    <div class="debug-item">
                        <strong>Analyse resultat:</strong> ${flowDebug.analysis}
                    </div>
                    <div class="debug-item">
                        <strong>Standardnummer funnet:</strong> ${flowDebug.standards.length > 0 ? flowDebug.standards.join(', ') : 'Ingen'}
                    </div>
                </div>
                
                <div class="debug-section">
                    <h5>🎯 2. OPTIMALISERING</h5>
                    <div class="debug-item">
                        <strong>Optimalisert spørsmål:</strong> "${flowDebug.optimized}"
                    </div>
                    <div class="debug-item">
                        <strong>Embeddings dimensjoner:</strong> ${flowDebug.embeddings_dim}
                    </div>
                </div>
                
                <div class="debug-section">
                    <h5>🔍 3. ELASTICSEARCH QUERY OBJEKT</h5>
                    <div class="debug-item">
                        <strong>Query type:</strong> ${this.getQueryType(flowDebug.route)}
                    </div>
                    <pre class="query-object">${JSON.stringify(flowDebug.query_object, null, 2)}</pre>
                </div>
                
                <div class="debug-section">
                    <h5>📚 4. SØKERESULTATER</h5>
                    <div class="debug-item">
                        <strong>Chunks funnet:</strong> ${flowDebug.chunks_count}
                    </div>
                    <div class="debug-item">
                        <strong>Elasticsearch took:</strong> ${generalDebug.elasticsearch_response?.took || 'N/A'}ms
                    </div>
                    <div class="debug-item">
                        <strong>Total hits:</strong> ${generalDebug.elasticsearch_response?.total_hits || 'N/A'}
                    </div>
                    <div class="debug-item">
                        <strong>Max score:</strong> ${generalDebug.elasticsearch_response?.max_score || 'N/A'}
                    </div>
                </div>
                
                <div class="debug-section">
                    <h5>📄 5. CHUNK PREVIEW</h5>
                    <div class="chunks-preview">
                        ${generalDebug.chunks_info?.chunks_preview?.map((chunk, i) => `
                            <div class="chunk-item">
                                <strong>Chunk ${i + 1}:</strong> Score: ${chunk.score.toFixed(3)}<br>
                                <strong>Reference:</strong> ${chunk.reference}<br>
                                <strong>Text:</strong> ${chunk.text_preview}
                            </div>
                        `).join('') || 'Ingen chunks å vise'}
                    </div>
                </div>
                
                <div class="debug-section">
                    <h5>📝 6. GENERERT SVAR</h5>
                    <div class="debug-item">
                        <strong>Svar lengde:</strong> ${generalDebug.answer_length} tegn
                    </div>
                    <div class="debug-item">
                        <strong>Total prosesseringstid:</strong> ${generalDebug.processing_time.toFixed(3)}s
                    </div>
                </div>
                
                <div class="debug-section">
                    <h5>🔧 7. TEKNISK INFO</h5>
                    <div class="debug-item">
                        <strong>Cache entries:</strong> ${generalDebug.cache_entries}
                    </div>
                    <div class="debug-item">
                        <strong>Input sanitized:</strong> ${generalDebug.input_sanitized}
                    </div>
                    <div class="debug-item">
                        <strong>Question length:</strong> ${generalDebug.question_length}
                    </div>
                </div>
                
                <div class="debug-section">
                    <h5>📦 8. RÅDATA - CHUNKS INNHOLD</h5>
                    <details class="raw-chunks">
                        <summary>Vis rådata for chunks (klikk for å utvide)</summary>
                        <pre class="chunks-raw">${flowDebug.chunks}</pre>
                    </details>
                </div>
                
                <div class="debug-section">
                    <h5>🔬 9. FULLSTENDIG DEBUG JSON</h5>
                    <details class="raw-debug">
                        <summary>Vis fullstendig debug objekt (klikk for å utvide)</summary>
                        <pre class="debug-raw">${JSON.stringify({flow: flowDebug, general: generalDebug}, null, 2)}</pre>
                    </details>
                </div>
            </div>
        `;
    }
    
    getQueryType(route) {
        switch(route) {
            case 'including': return 'Filter Query (Standard numbers with embeddings)';
            case 'without': return 'Textual Query (Multi-match with embeddings)';
            case 'personal': return 'Personal Handbook Query (Filter with embeddings)';
            default: return 'Unknown';
        }
    }
    
    formatAnswer(answer) {
        if (!answer) return '<p class="no-answer">Ingen svar funnet.</p>';
        
        // Convert markdown-like formatting to HTML
        let formatted = answer
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n/g, '<br>');
        
        return `<p>${formatted}</p>`;
    }
    
    displayError(message) {
        this.elements.answerContent.innerHTML = `
            <div class="error-message">
                <h4>❌ Feil oppstod</h4>
                <p>${message}</p>
                <button class="btn btn-secondary mt-2" onclick="app.focusInput()">
                    Prøv igjen
                </button>
            </div>
        `;
        
        this.elements.debugContent.textContent = `Error: ${message}`;
        this.showResults();
        
        // Announce error to screen readers
        this.announceToScreenReader(`Feil: ${message}`);
    }
    
    showResults() {
        this.elements.resultsContainer.style.display = 'block';
        this.updateDebugVisibility();
    }
    
    hideResults() {
        this.elements.resultsContainer.style.display = 'none';
    }
    
    toggleDebug() {
        this.debugVisible = !this.debugVisible;
        this.updateDebugVisibility();
    }
    
    updateDebugVisibility() {
        const debugCard = document.querySelector('.debug-card');
        if (debugCard) {
            debugCard.style.display = this.debugVisible ? 'block' : 'none';
        }
        
        this.elements.debugToggle.textContent = this.debugVisible ? 
            '🔍 Skjul Debug' : '🔍 Vis Debug';
    }
    
    clearAll() {
        this.elements.questionInput.value = '';
        this.hideResults();
        this.elements.debugContent.innerHTML = '';
        this.elements.answerContent.innerHTML = '';
        this.focusInput();
        
        // Cancel any ongoing request
        this.cancelRequest();
        
        // Announce to screen readers
        this.announceToScreenReader('Innhold ryddet');
    }
    
    focusInput() {
        this.elements.questionInput.focus();
        
        // Move cursor to end
        const length = this.elements.questionInput.value.length;
        this.elements.questionInput.setSelectionRange(length, length);
    }
    
    announceToScreenReader(message) {
        const announcement = document.createElement('div');
        announcement.setAttribute('aria-live', 'polite');
        announcement.setAttribute('aria-atomic', 'true');
        announcement.className = 'sr-only';
        announcement.textContent = message;
        
        document.body.appendChild(announcement);
        
        // Remove after announcement
        setTimeout(() => {
            document.body.removeChild(announcement);
        }, 1000);
    }
    
    getOrCreateSessionId() {
        let sessionId = localStorage.getItem('standardgpt_session_id');
        if (!sessionId) {
            sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 8)}`;
            localStorage.setItem('standardgpt_session_id', sessionId);
        }
        console.log('Session ID:', sessionId);
        return sessionId;
    }
    
    clearSession() {
        localStorage.removeItem('standardgpt_session_id');
        this.sessionId = this.getOrCreateSessionId();
        console.log('New session created:', this.sessionId);
    }
    
    // NY: Metode for ny samtale (clear session)
    startNewConversation() {
        this.clearAll();
        this.clearSession();
        
        // Send signal til backend om å cleare session
        fetch('/api/session/clear', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Session-ID': this.sessionId
            }
        }).catch(console.error);
        
        this.announceToScreenReader('Ny samtale startet');
    }
}

// Initialize app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.app = new StandardGPTApp();
});

// Service Worker registration for PWA capabilities
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/static/js/sw.js')
            .then(registration => {
                console.log('SW registered: ', registration);
            })
            .catch(registrationError => {
                console.log('SW registration failed: ', registrationError);
            });
    });
}

// Export for testing
if (typeof module !== 'undefined' && module.exports) {
    module.exports = StandardGPTApp;
} 