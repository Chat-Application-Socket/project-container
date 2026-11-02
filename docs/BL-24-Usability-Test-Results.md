# BL-24: Cross-Browser/OS and Usability Test Results

## 1. Objective
Check the chat application's browser compatibility, operating-system compatibility, and ease of use for first-time users.

## 2. Test Environment
- Operating system: Windows
- Browsers tested: Microsoft Edge, Google Chrome, Mozilla Firefox
- Local server: Flask development server
- Test date: 2 November 2026

## 3. Test Results

| Test | Actual Result | Status |
|---|---|---|
| Open the chat application in Microsoft Edge | Application loaded successfully | Pass |
| Connect to the chat server | Connection succeeded after fixing a duplicate JavaScript declaration | Pass |
| Send a chat message | Test message appeared in the chat area | Pass |
| Check the chat interface | Removed a visible Git conflict marker from `templates/index.html` | Pass after fix |
| Google Chrome compatibility | Application connected successfully and messages were displayed | Pass |
| Mozilla Firefox compatibility | Application connected successfully and messages were displayed | Pass |
| Cross-browser message broadcast | A test message appeared in Edge, Chrome, and Firefox | Pass |
| First-time-user usability test with 3 volunteers | Not yet performed | Not tested |
| Safari compatibility, if available | Not tested | Not tested |
| Compatibility on a second operating system | Linux setup blocked by missing Ubuntu packages | Not tested |

## 4. Issues Found and Fixed
1. `static/client.js` declared `messageList` twice, causing a JavaScript syntax error. Removed the duplicate declaration.
2. `templates/index.html` contained a visible `<<<<<<< HEAD` conflict marker. Removed the marker.

## 5. Automated Checks
- Pytest: 74 passed, 1 skipped, 0 failed (previously recorded result).
- Flake8: Passed with no output (previously recorded result).
- `git diff --check`: Passed with no output (previously recorded result).

## 6. Conclusion
The basic connection and messaging workflow was verified on Windows using Microsoft Edge, Google Chrome, and Mozilla Firefox. A test message was successfully displayed across all three browsers. The previously recorded automated tests and code-quality check passed. Testing on a second operating system and usability testing with three first-time users remain pending. Safari was not tested. Full BL-24 acceptance should not be claimed until the remaining required tests are completed.
