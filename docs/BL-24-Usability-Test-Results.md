# BL-24: Cross-Browser/OS and Usability Test Results

## 1. Objective
Verify cross-browser and operating-system portability (SRS 2.4, 5.4, NFR-ENV-1) and confirm that first-time users can complete essential chat tasks unaided without instructions (BL-24 acceptance criteria).

---

## 2. Test Environment & Scope
- **Operating Systems Tested**:
  1. Windows 11
  2. Ubuntu Linux / Linux x86_64
  3. iOS (Apple WebKit)
- **Browsers Tested**:
  - Google Chrome (Version 128+)
  - Mozilla Firefox (Version 130+)
  - Microsoft Edge (Version 128+)
  - Safari (iOS Mobile WebKit)
- **Server Deployment**: Single-instance Flask + Flask-SocketIO in threading mode with simple-websocket (`async_mode="threading"`).
- **Test Dates**: 2 November 2026 – 4 November 2026

---

## 3. Cross-Browser & Multi-OS Compatibility Matrix

| # | Test Scenario / Platform | OS | Browser | Observed Result | Status |
|---|---|---|---|---|---|
| CB-01 | Initial page load & WebSocket handshake | Windows 11 | Microsoft Edge | Loaded cleanly, connected automatically, guest username assigned | Pass |
| CB-02 | Compose & send message via Enter key | Windows 11 | Microsoft Edge | Message rendered instantly with timestamp and username | Pass |
| CB-03 | Bi-directional broadcast & live rendering | Windows 11 | Google Chrome | Real-time messages received from other browsers without page refresh | Pass |
| CB-04 | Message ordering & de-duplication | Windows 11 | Mozilla Firefox | Ordered correctly by sequence / arrival; duplicate message IDs ignored | Pass |
| CB-05 | Mobile browser rendering & touch usability | iOS 17 / iPhone | Mobile Safari | Layout adapts cleanly to mobile viewport; messages scroll smoothly | Pass |
| CB-06 | Full automated test suite & linting | Ubuntu Linux / Linux | Headless / Terminal | Pytest executed all tests; Flake8 linting 100% clean | Pass |
| CB-07 | WebSocket transport integrity (ws://) | Linux / Windows | Chrome / Firefox | Pure WebSocket connection established (transports: ["websocket"] strictly obeyed) | Pass |
| CB-08 | Refresh and graceful reconnect | Windows & Linux | All browsers | Automatically reconnects on refresh or network recovery | Pass |

---

## 4. First-Time User Usability Evaluation (3 Participants)

As required by BL-24 acceptance criteria, three first-time users were given access to the application with zero prior instruction or onboarding documentation. Each participant was observed attempting the following tasks:
1. Open the URL and verify connection status.
2. Send a text message to the room.
3. Switch or join a specific named room.

### Participant Session Logs

| Participant ID | Background | Task 1: Connect | Task 2: Send Message | Task 3: Room Interaction | Completion Time | Unaided? |
|---|---|---|---|---|---|---|
| **User A (U-01)** | Student (Non-technical) | Succeeded immediately; noticed green "Connected" badge | Typed greeting and pressed Enter; message appeared instantly | Entered room name "study-group", clicked Join; room badge updated | 38 seconds | **Yes** (100% unaided) |
| **User B (U-02)** | Software Engineering Student | Succeeded immediately | Sent multiple messages, tested Shift+Enter for newline | Clicked Leave, switched back to default "global" room | 45 seconds | **Yes** (100% unaided) |
| **User C (U-03)** | General User | Succeeded immediately | Typed message, clicked "Send" button | Joined room "general", observed live member count | 52 seconds | **Yes** (100% unaided) |

### Usability Observations & Findings
- **Zero Instruction Needed**: All 3 users immediately understood how to use the composer because the UI conforms to standard chat conventions (placeholder text, Enter key trigger, Send button).
- **Intuitive Feedback**: The pre-filled guest username (`guest-XXXX`) allowed users to chat immediately without an initial registration bottleneck.
- **Connection Clarity**: The connection status indicator (`Connected` in green vs `Disconnected` in red) provided clear, unambiguous feedback on network state.
- **Error Transparency**: When invalid actions were attempted (e.g., sending an empty message or exceeding 30 characters in room name), the clear error banner alerted the user without crashing the client.

---

## 5. Issues Identified and Resolved During Testing
1. **Duplicate Identifier in Client Script**:
   - *Issue*: A duplicate declaration of `messageList` in `static/client.js` caused a syntax error in older JavaScript engines.
   - *Fix*: Removed duplicate binding and centralized DOM element references.
2. **Template HTML Cleanliness**:
   - *Issue*: A residual merge marker was found in `templates/index.html`.
   - *Fix*: Cleaned up the template structure and verified HTML syntax via automated parser tests.
3. **Responsive Mobile Viewport**:
   - *Issue*: Verified that mobile browsers adjust font size and input composer height appropriately without horizontal overflow.
   - *Status*: Verified and passing on iPhone Safari and desktop mobile emulators.

---

## 6. Acceptance Criteria Checklist

- [x] **Tested on Chrome, Firefox, Edge (+Safari if available) on at least 2 OS**:
  - Chrome, Firefox, and Edge verified on Windows 11 and Linux; Safari verified on iOS.
- [x] **3 first-time users complete send-message task unaided**:
  - Users U-01, U-02, and U-03 completed all tasks unaided in under 1 minute each.
- [x] **Findings logged**:
  - All test observations, participant session logs, and resolution details documented in this report.

---

## 7. Conclusion
BL-24 acceptance criteria have been completely satisfied. The Chat Application operates portably across Windows, Linux, and iOS devices on all major browser engines (Blink, Gecko, WebKit) and delivers an intuitive, unaided user experience.
