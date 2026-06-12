/* ==============================================================================
   Solstice Pilates AI Receptionist - Frontend JavaScript Engine
   Supports modern POST-based Server-Sent Events (SSE) decoding, dynamic 
   visualizer bindings, tab switches, and live database sync.
   ============================================================================== */

document.addEventListener("DOMContentLoaded", () => {
    // STATE MANAGERS
    let phone = "415-555-0190";
    let chatHistory = [];
    let activeTab = "calendar-tab";
    let selectedDate = "2026-05-28";
    let isGenerating = false;

    // DOM ELEMENTS
    const themeToggle = document.getElementById("theme-toggle");
    const callerPhoneInput = document.getElementById("caller-phone");
    const pickerTags = document.querySelectorAll(".picker-tag");
    
    const chatBox = document.getElementById("chat-box");
    const chatForm = document.getElementById("chat-form");
    const chatInput = document.getElementById("chat-input");
    const sendButton = document.getElementById("send-button");
    
    const activityBar = document.getElementById("activity-bar");
    const activityStatus = document.getElementById("activity-status");
    const handoffBanner = document.getElementById("handoff-banner");
    const handoffReason = document.getElementById("handoff-reason");
    
    const llmBadge = document.getElementById("llm-badge");
    const llmText = document.getElementById("llm-text");
    const calendarBadge = document.getElementById("calendar-badge");
    const calendarText = document.getElementById("calendar-text");
    const sheetsBadge = document.getElementById("sheets-badge");
    const sheetsText = document.getElementById("sheets-text");
    
    const tabBtns = document.querySelectorAll(".tab-btn");
    const tabPanes = document.querySelectorAll(".tab-pane");
    const calendarDatePicker = document.getElementById("calendar-date-picker");
    const resetDbBtn = document.getElementById("reset-db-btn");
    
    const calendarVisualList = document.getElementById("calendar-visual-list");
    const contactsVisualList = document.getElementById("contacts-visual-list");
    const logsVisualList = document.getElementById("logs-visual-list");

    // ==============================================================================
    // Theme Engine (Dark/Light Modes)
    // ==============================================================================
    themeToggle.addEventListener("click", () => {
        const currentTheme = document.documentElement.getAttribute("data-theme");
        const nextTheme = currentTheme === "dark" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", nextTheme);
        
        const icon = themeToggle.querySelector("i");
        if (nextTheme === "dark") {
            icon.className = "fa-solid fa-moon";
        } else {
            icon.className = "fa-solid fa-sun";
        }
    });

    // ==============================================================================
    // Tab Controllers
    // ==============================================================================
    tabBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            tabBtns.forEach(b => b.classList.remove("active"));
            tabPanes.forEach(p => p.classList.remove("active"));
            
            btn.classList.add("active");
            activeTab = btn.getAttribute("data-tab");
            document.getElementById(activeTab).classList.add("active");
            
            refreshVisualizers();
        });
    });

    // ==============================================================================
    // Caller Simulators
    // ==============================================================================
    // Handle manual phone number change
    callerPhoneInput.addEventListener("change", (e) => {
        phone = e.target.value.trim();
        resetChatHistory();
        
        // Remove active class from picker tags if none match
        pickerTags.forEach(tag => {
            if (tag.getAttribute("data-phone") === phone) {
                tag.classList.add("active");
            } else {
                tag.classList.remove("active");
            }
        });
    });

    // Handle tag selections (Sara/Jessica)
    pickerTags.forEach(tag => {
        tag.addEventListener("click", () => {
            pickerTags.forEach(t => t.classList.remove("active"));
            tag.classList.add("active");
            
            phone = tag.getAttribute("data-phone");
            callerPhoneInput.value = phone;
            
            resetChatHistory();
            
            // Focus on chat input
            chatInput.focus();
        });
    });

    function resetChatHistory() {
        chatHistory = [];
        handoffBanner.style.display = "none";
        
        // Re-inject initial system instruction & welcome bubble
        chatBox.innerHTML = `
            <div class="system-bubble">
                <i class="fa-solid fa-shield-halved"></i>
                <p><strong>System Aura Initialized:</strong> Simulated caller updated to <strong>${phone}</strong>. Aura will automatically query and record your session detail in call sheets.</p>
            </div>
            
            <div class="message assistant">
                <div class="message-avatar"><i class="fa-solid fa-headset"></i></div>
                <div class="message-content">
                    <p>Thank you for calling Solstice Pilates! My name is Aura. How can I help you today?</p>
                </div>
            </div>
        `;
        chatBox.scrollTop = chatBox.scrollHeight;
        refreshVisualizers();
    }

    // ==============================================================================
    // API Synchronizers
    // ==============================================================================
    
    // Fetch Active Configuration Details
    async function loadSystemConfig() {
        try {
            const res = await fetch("/api/config");
            const data = await res.json();
            
            // LLM Configuration rendering
            llmText.textContent = `LLM: ${data.llm_provider.toUpperCase()} (${data.llm_model})`;
            llmBadge.title = `Model: ${data.llm_model} | URL: ${data.spreadsheet_id}`;
            
            // Calendar Integration Badge
            if (data.calendar_connected) {
                calendarText.textContent = "Calendar: Google Live";
                calendarBadge.className = "status-badge connected";
            } else {
                calendarText.textContent = "Calendar: Mock DB Active";
                calendarBadge.className = "status-badge mock";
            }
            
            // Sheets Integration Badge
            if (data.sheets_connected) {
                sheetsText.textContent = "Sheets: Google Live";
                sheetsBadge.className = "status-badge connected";
            } else {
                sheetsText.textContent = "Sheets: Mock DB Active";
                sheetsBadge.className = "status-badge mock";
            }
        } catch (err) {
            console.error("Error fetching system configuration: ", err);
        }
    }

    // Load Calendar Classes State
    async function loadCalendarState() {
        try {
            const date = calendarDatePicker.value || selectedDate;
            selectedDate = date;
            
            const res = await fetch(`/api/calendar?date=${date}`);
            if (!res.ok) throw new Error("API error");
            const data = await res.json();
            
            calendarVisualList.innerHTML = "";
            
            if (!data.classes || data.classes.length === 0) {
                calendarVisualList.innerHTML = `
                    <div class="empty-state">
                        <i class="fa-regular fa-calendar-xmark"></i>
                        No classes found on this date. Select another day.
                    </div>
                `;
                return;
            }

            data.classes.forEach(cls => {
                const spotsLeft = cls.capacity - cls.booked_count;
                const isFull = spotsLeft <= 0;
                
                const card = document.createElement("div");
                card.className = "class-card";
                
                // Construct attendee elements
                let attendeePills = "";
                if (cls.attendees && cls.attendees.length > 0) {
                    cls.attendees.forEach(att => {
                        const isCurrentCaller = att.phone.replace(/\D/g, '') === phone.replace(/\D/g, '');
                        attendeePills += `
                            <div class="attendee-pill ${isCurrentCaller ? 'caller' : ''}" title="${att.phone}">
                                <i class="fa-solid ${isCurrentCaller ? 'fa-phone' : 'fa-user'}"></i>
                                ${att.name}
                            </div>
                        `;
                    });
                } else {
                    attendeePills = `<span class="no-attendees">No bookings yet</span>`;
                }

                card.innerHTML = `
                    <div class="class-card-header">
                        <div class="class-info">
                            <h4>${cls.name}</h4>
                            <p><i class="fa-regular fa-clock"></i> ${cls.time} &nbsp;|&nbsp; <i class="fa-solid fa-chalkboard-user"></i> ${cls.instructor}</p>
                        </div>
                        <span class="class-spots ${isFull ? 'full' : 'available'}">
                            ${isFull ? 'FULL' : `${spotsLeft} SPOTS LEFT`}
                        </span>
                    </div>
                    <div class="class-card-attendees">
                        <div class="attendees-title">Attendees (${cls.booked_count}/${cls.capacity})</div>
                        <div class="attendee-list">
                            ${attendeePills}
                        </div>
                    </div>
                `;
                
                calendarVisualList.appendChild(card);
            });
        } catch (err) {
            console.error("Error loading calendar visualizer: ", err);
            calendarVisualList.innerHTML = `<div class="empty-state" style="color:var(--color-danger);"><i class="fa-solid fa-triangle-exclamation"></i> Sync Failure.</div>`;
        }
    }

    // Load Sheets State (Contacts & Call Logs)
    async function loadSheetsState() {
        try {
            const res = await fetch("/api/sheets");
            if (!res.ok) throw new Error("API error");
            const data = await res.json();
            
            // Populate Contacts
            contactsVisualList.innerHTML = "";
            if (!data.contacts || data.contacts.length === 0) {
                contactsVisualList.innerHTML = `
                    <tr><td colspan="4" class="empty-state" style="text-align:center;"><i class="fa-solid fa-address-book"></i> No registered contacts yet.</td></tr>
                `;
            } else {
                data.contacts.forEach(c => {
                    const row = document.createElement("tr");
                    const dateObj = new Date(c["Created At"]);
                    const formattedDate = dateObj.toLocaleDateString() + " " + dateObj.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
                    
                    row.innerHTML = `
                        <td class="contact-name-cell">${c["Name"]}</td>
                        <td><strong>${c["Phone"]}</strong></td>
                        <td>${c["Email"] || '<span class="text-muted">N/A</span>'}</td>
                        <td class="contact-notes-cell" title="${c['Notes']}">${c["Notes"] || '<span class="text-muted">-</span>'}</td>
                    `;
                    contactsVisualList.appendChild(row);
                });
            }

            // Populate Call Logs
            logsVisualList.innerHTML = "";
            if (!data.call_logs || data.call_logs.length === 0) {
                logsVisualList.innerHTML = `
                    <div class="empty-state">
                        <i class="fa-solid fa-receipt"></i>
                        No calls recorded in this session.
                    </div>
                `;
            } else {
                // Reverse log list to show newest on top
                const reversedLogs = [...data.call_logs].reverse();
                reversedLogs.forEach(log => {
                    const card = document.createElement("div");
                    const isHandoff = log["Handoff Required"];
                    card.className = `log-card ${isHandoff ? 'handoff' : ''}`;
                    
                    const dateObj = new Date(log["Created At"]);
                    const timeStr = dateObj.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
                    
                    card.innerHTML = `
                        <div class="log-card-header">
                            <div class="log-caller">
                                <h4>${log["Name"]}</h4>
                                <p><i class="fa-solid fa-hashtag"></i> ${log["Phone"]}</p>
                            </div>
                            <span class="log-date">${timeStr}</span>
                        </div>
                        <div class="log-card-body">
                            <p>${log["Summary"]}</p>
                            ${isHandoff ? `
                                <div style="display:flex; justify-content:space-between; align-items:center; margin-top:8px;">
                                    <span class="log-card-badge alert"><i class="fa-solid fa-circle-exclamation"></i> Escalated</span>
                                    <span style="font-size:11px; font-weight:500; color:var(--color-danger); max-width:70%; overflow:hidden; text-overflow:ellipsis;" title="${log['Handoff Reason']}">
                                        ${log['Handoff Reason']}
                                    </span>
                                </div>
                            ` : ''}
                        </div>
                    `;
                    logsVisualList.appendChild(card);
                });
            }
        } catch (err) {
            console.error("Error loading sheets visualizer: ", err);
            contactsVisualList.innerHTML = `<tr><td colspan="4" style="color:var(--color-danger); text-align:center;">Sync Failure.</td></tr>`;
            logsVisualList.innerHTML = `<div class="empty-state" style="color:var(--color-danger);"><i class="fa-solid fa-triangle-exclamation"></i> Sync Failure.</div>`;
        }
    }

    function refreshVisualizers() {
        loadCalendarState();
        loadSheetsState();
    }

    // Calendar Date Picker Listener
    calendarDatePicker.addEventListener("change", () => {
        loadCalendarState();
    });

    // Reset Mock Database trigger
    resetDbBtn.addEventListener("click", async () => {
        if (confirm("Are you sure you want to reset all mock calendar spots and caller sheet data to default values? This clears current conversation test state.")) {
            try {
                const res = await fetch("/api/reset", { method: "POST" });
                const data = await res.json();
                if (data.status === "success") {
                    alert("Local JSON Mock Databases successfully reset!");
                    resetChatHistory();
                }
            } catch (err) {
                alert("Failed to reset databases: " + err);
            }
        }
    });

    // ==============================================================================
    // Streaming SSE Chat Controllers
    // ==============================================================================
    chatForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const messageText = chatInput.value.trim();
        if (!messageText || isGenerating) return;
        
        chatInput.value = "";
        isGenerating = true;
        sendButton.disabled = true;
        
        // Append caller message
        appendMessage("user", messageText);
        
        // Setup receptionist bubble placeholder
        const assistantBubbleId = appendStreamingMessagePlaceholder();
        const assistantTextContainer = document.getElementById(assistantBubbleId);
        
        // Show Agent thinking spinner
        activityBar.style.display = "block";
        activityStatus.textContent = "Agent planning response...";
        
        try {
            // Send payload via Fetch with ReadableStream
            const response = await fetch("/api/chat/stream", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    message: messageText,
                    history: chatHistory,
                    phone: phone
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP Error ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            
            let accumulatedResponse = "";
            let done = false;
            let buffer = "";

            while (!done) {
                const { value, done: streamDone } = await reader.read();
                done = streamDone;
                
                if (value) {
                    const chunk = decoder.decode(value);
                    buffer += chunk;
                    
                    // Parse Event Stream Lines
                    const lines = buffer.split("\n\n");
                    // Keep the last partial segment in the buffer
                    buffer = lines.pop(); 
                    
                    for (const line of lines) {
                        if (line.trim().startsWith("data: ")) {
                            try {
                                const parsed = JSON.parse(line.replace("data: ", ""));
                                
                                if (parsed.type === "token") {
                                    accumulatedResponse += parsed.content;
                                    assistantTextContainer.innerHTML = accumulatedResponse.replace(/\n/g, "<br>");
                                    chatBox.scrollTop = chatBox.scrollHeight;
                                } 
                                else if (parsed.type === "status") {
                                    // Update receptionist activity banner
                                    activityStatus.textContent = parsed.content;
                                } 
                                else if (parsed.type === "handoff") {
                                    // Trigger immediate visual handoff banner
                                    handoffBanner.style.display = "flex";
                                    handoffReason.textContent = parsed.content;
                                    
                                    // Add alert bubble in chat
                                    appendSystemAlert(`🚨 Escaling booking to studio manager. Reason: "${parsed.content}"`);
                                    
                                    // Refresh visual log sheets immediately
                                    loadSheetsState();
                                } 
                                else if (parsed.type === "error") {
                                    assistantTextContainer.innerHTML += `<br><span style="color:var(--color-danger);">[System Error: ${parsed.content}]</span>`;
                                }
                            } catch (pe) {
                                console.error("Error parsing stream chunk: ", pe);
                            }
                        }
                    }
                }
            }

            // Chat exchange complete! Save this turn in conversation history
            chatHistory.push({ role: "user", content: messageText });
            chatHistory.push({ role: "assistant", content: accumulatedResponse });
            
            // Clean up activity loader
            activityBar.style.display = "none";
            
            // Refresh Visual Databases
            refreshVisualizers();

        } catch (err) {
            console.error("Fatal chat error: ", err);
            assistantTextContainer.innerHTML = `<span style="color:var(--color-danger); font-weight:600;"><i class="fa-solid fa-triangle-exclamation"></i> Server Sync Failure</span><br>Verify your server connection and .env configurations.`;
            activityBar.style.display = "none";
        } finally {
            isGenerating = false;
            sendButton.disabled = false;
        }
    });

    function appendMessage(role, text) {
        const msgDiv = document.createElement("div");
        msgDiv.className = `message ${role}`;
        
        const avatarIcon = role === "user" ? "fa-phone" : "fa-headset";
        
        msgDiv.innerHTML = `
            <div class="message-avatar"><i class="fa-solid ${avatarIcon}"></i></div>
            <div class="message-content">
                <p>${text}</p>
            </div>
        `;
        chatBox.appendChild(msgDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    function appendStreamingMessagePlaceholder() {
        const bubbleId = `stream_${Date.now()}`;
        const msgDiv = document.createElement("div");
        msgDiv.className = "message assistant";
        
        msgDiv.innerHTML = `
            <div class="message-avatar"><i class="fa-solid fa-headset"></i></div>
            <div class="message-content">
                <p id="${bubbleId}"><span class="text-muted">Aura is typing...</span></p>
            </div>
        `;
        chatBox.appendChild(msgDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
        return bubbleId;
    }

    function appendSystemAlert(text) {
        const alertDiv = document.createElement("div");
        alertDiv.className = "system-bubble";
        alertDiv.style.border = "1px solid hsla(354, 75%, 55%, 0.25)";
        alertDiv.style.background = "hsla(354, 75%, 55%, 0.05)";
        
        alertDiv.innerHTML = `
            <i class="fa-solid fa-circle-exclamation" style="color:var(--color-danger);"></i>
            <p style="color:var(--color-danger); font-weight:600;">${text}</p>
        `;
        chatBox.appendChild(alertDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    // ==============================================================================
    // INITIALIZATION RUNS
    // ==============================================================================
    loadSystemConfig();
    refreshVisualizers();
    
    // Automatically poll changes in the databases every 5 seconds to keep tabs synchronized
    setInterval(() => {
        if (!isGenerating) {
            refreshVisualizers();
        }
    }, 5000);
});
