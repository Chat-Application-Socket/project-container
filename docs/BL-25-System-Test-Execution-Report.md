\# BL-25 – System Test Execution Report



\## 1. Test Execution Details



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



\## 2. Automated Test Execution



Command executed:



`python -m pytest -v`



Actual result:



\- 82 tests passed successfully.

\- 1 test was skipped because Node.js was unavailable.

\- 0 tests failed.

\- Execution time: 0.76 seconds.



The skipped test was:



`tests/test\_message\_order.py::test\_message\_store\_orders\_and\_deduplicates`



The test was skipped because Node.js was unavailable in the environment.



\## 3. Additional Code Quality Check



Command executed:



`python -m flake8`



Actual result: No linting errors were reported.



\## 4. Test Coverage



The automated test suite covered the following areas:



| Test file | Coverage |

|---|---|

| test\_broadcast.py | Room-based message broadcasting and timestamps |

| test\_chat\_ui.py | Chat interface and accessibility |

| test\_connection.py | Connection and disconnection handling |

| test\_message\_order.py | Message ordering and rendering |

| test\_message\_schema.py | Message structure and validation |

| test\_message\_validation.py | Empty, invalid and malformed messages |

| test\_rooms.py | Room joining, leaving and isolation |

| test\_smoke.py | Application startup |

| test\_xss\_protection.py | XSS protection and safe message rendering |



\## 5. Test Plan Execution Status



The original Test Plan contains 98 test cases:



\- 80 functional test cases (REQ-1 to REQ-10).

\- 18 non-functional test cases (NT-01 to NT-18).



The automated test suite passed 82 tests. However, the available pytest output does not establish a one-to-one mapping between those 82 tests and all 98 Test Plan case IDs.



Therefore, individual Test Plan cases have not been marked as passed without supporting evidence. Manual execution and case-by-case verification remain pending.



\## 6. Final Summary



| Result | Count |

|---|---:|

| Automated tests passed | 82 |

| Automated tests failed | 0 |

| Automated tests skipped | 1 |

| Total automated tests | 83 |

| Test Plan cases | 98 |

| Test Plan cases individually verified | Pending |



\## 7. Conclusion



The automated test suite completed successfully with 82 passed tests, 1 skipped test and 0 failures. Flake8 also reported no errors.



Further manual execution and verification are required to complete all 98 test cases listed in the original Test Plan.



\*\*Report status:\*\* Automated testing completed; full Test Plan execution pending.

