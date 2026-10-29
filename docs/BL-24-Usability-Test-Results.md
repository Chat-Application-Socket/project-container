\# BL-24: Cross-Browser/OS and Usability Test Results



\## 1. Objective

Check the chat application's browser compatibility, operating-system compatibility, and ease of use for first-time users.



\## 2. Test Environment

\- Operating system: Windows

\- Browser tested: Microsoft Edge

\- Local server: Flask development server

\- Test date: 29 October 2026



\## 3. Test Results



| Test | Actual Result | Status |

|---|---|---|

| Open the chat application in Edge | Application loaded successfully | Pass |

| Connect to the chat server | Connection succeeded after fixing a duplicate JavaScript declaration | Pass |

| Send a chat message | Test message appeared in the chat area | Pass |

| Check the chat interface | Removed a visible Git conflict marker from `templates/index.html` | Pass after fix |

| First-time-user usability test with 3 volunteers | Not yet performed | Not tested |

| Chrome compatibility | Not yet tested | Not tested |

| Firefox compatibility | Not yet tested | Not tested |

| Safari compatibility, if available | Not yet tested | Not tested |

| Compatibility on a second operating system | Not yet tested | Not tested |



\## 4. Issues Found and Fixed

1\. `static/client.js` declared `messageList` twice, causing a JavaScript syntax error. Removed the duplicate declaration.

2\. `templates/index.html` contained a visible `<<<<<<< HEAD` conflict marker. Removed the marker.



\## 5. Automated Checks

\- Pytest: 74 passed, 1 skipped, 0 failed.

\- Flake8: Passed with no output.

\- `git diff --check`: Passed with no output.



\## 6. Conclusion

The basic connection and messaging workflow was verified in Microsoft Edge on Windows. Automated tests and the code-quality check passed. Cross-browser testing, second-operating-system testing, and testing with three first-time users remain pending. These tests must be completed before claiming full BL-24 acceptance.
