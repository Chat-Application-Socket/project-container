# BL-25 – System Test Execution Report



## 1. Test Execution Details



| Item | Details |

|---|---|

| Project | Chat Application |

| Backlog ID | BL-25 |

| Branch | `bl-25-test-execution` |

| Test environment | Windows, Python 3.12.3 |

| Test framework | pytest 9.1.1 |

| Total automated tests collected | 83 |

| Automated tests passed | 82 |

| Automated tests failed | 0 |

| Automated tests skipped | 1 |



## 2. Automated Test Execution



Command executed:



`python -m pytest -v`



Actual result:



- 82 tests passed successfully.

- 1 test was skipped because Node.js was unavailable.

- 0 tests failed.

- Execution time: 0.76 seconds.



The skipped test was:



`tests/test_message_order.py::test_message_store_orders_and_deduplicates`



The test was skipped because Node.js was unavailable in the environment.



## 3. Additional Code Quality Check



Command executed:



`python -m flake8`



Actual result: No linting errors were reported.



## 4. Test Coverage



The automated test suite covered the following areas:



| Test file | Coverage |

|---|---|

| test_broadcast.py | Room-based message broadcasting and timestamps |

| test_chat_ui.py | Chat interface and accessibility |

| test_connection.py | Connection and disconnection handling |

| test_message_order.py | Message ordering and rendering |

| test_message_schema.py | Message structure and validation |

| test_message_validation.py | Empty, invalid and malformed messages |

| test_rooms.py | Room joining, leaving and isolation |

| test_smoke.py | Application startup |

| test_xss_protection.py | XSS protection and safe message rendering |



## 5. Test Plan Execution Status



The original Test Plan contains 98 test cases:



- 80 functional test cases (REQ-1 to REQ-10).

- 18 non-functional test cases (NT-01 to NT-18).



The automated test suite passed 82 tests. However, the available pytest output does not establish a one-to-one mapping between those 82 tests and all 98 Test Plan case IDs.



Therefore, individual Test Plan cases have not been marked as passed without supporting evidence. The case-by-case matrix records 25 Pass, 2 Fail and 71 Not Run. These counts reflect the evidence recorded so far; they do not mean all 98 cases were executed.



## 6. Final Summary



| Result | Count |

|---|---:|

| Automated tests passed | 82 |

| Automated tests failed | 0 |

| Automated tests skipped | 1 |

| Total automated tests | 83 |

| Test Plan cases | 98 |

| Test Plan cases marked Pass | 25 |
| Test Plan cases marked Fail | 2 |
| Test Plan cases marked Not Run | 71 |
| Total Test Plan cases | 98 |



## 7. Conclusion



The automated test suite completed successfully with 82 passed tests, 1 skipped test and 0 failures. Flake8 also reported no errors.



The matrix records 25 Pass, 2 Fail and 71 Not Run out of 98 Test Plan cases. Further execution is required, and the two failed cases must be reviewed.



**Report status:** Automated testing completed; partial Test Plan execution recorded; 71 cases remain Not Run.


## 8. Manual Verification Evidence

| Check | Actual result | Status |
|---|---|---|
| Application connection | Browser displayed Connected | Observed pass |
| Send a message | Message appeared in chat | Observed pass |
| Disconnected state | Status displayed Disconnected and message input was disabled | Observed pass |
| Join a room | Room badge displayed the selected room | Observed pass |
| Leave a room | Room badge changed to Room: none | Observed pass |
| Room isolation | Messages appeared in the matching room, not the other room | Observed pass |
| Disconnected client | Input was disabled; the disconnected tab did not display a new message from the connected tab | Partially verified |

## 9. Non-Functional Test Status

| Test ID | Status | Evidence or reason |
|---|---|---|
| NT-01 | Not tested | 100-user load and p95 latency not measured |
| NT-02 | Not tested | 50-message baseline latency not measured |
| NT-03 | Not tested | 100 connections for five minutes not tested |
| NT-04 | Not tested | Ramp test to 120 connections not performed |
| NT-05 | Not fully verified | README documents HTTPS/WSS setup; production TLS was not verified |
| NT-06 | Not tested | Insecure WebSocket rejection was not tested against a deployed host |
| NT-07 | Automated supporting evidence | XSS protection test suite passed; exact test-plan case not independently verified |
| NT-08 | Automated supporting evidence | XSS protection test suite passed; exact test-plan case not independently verified |
| NT-09 | Not fully verified | Exact specified sanitization payload was not checked manually |
| NT-10 | Feature gap identified | Automatic reconnection is disabled in static/client.js |
| NT-11 | Not fully verified | Automatic recovery after network interruption was not tested |
| NT-12 | Not fully verified | Recovery when the server starts after the client was not tested |
| NT-13 | Not tested | Three first-time volunteers were not tested |
| NT-14 | Partially verified | Disconnected status was observed; all required error scenarios were not checked |
| NT-15 | Not fully tested | Edge on Windows was tested; other browsers were not verified |
| NT-16 | Not tested | Cross-platform instructions exist, but a second operating system was not tested |
| NT-17 | Not formally reviewed | A documented modularity review was not completed |
| NT-18 | Partially verified | Input was disabled and the disconnected tab did not display a new message; attempted-send error was not verified |

## 10. Overall Test Plan Status

The original Test Plan contains 98 cases: 80 functional cases and 18 non-functional cases. Automated results and selected manual observations provide evidence for some requirements, but a complete case-by-case execution matrix has not been completed.

**Report status:** Automated testing completed; selected manual checks recorded; full Test Plan execution remains incomplete. Performance, production TLS, multi-OS, and volunteer usability tests remain unverified.
