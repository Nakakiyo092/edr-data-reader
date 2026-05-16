# Design Philosophy and NegRes Handling

## Tool Positioning

- Purpose: Reading EDR data (not intended as an aid for protocol analysis)
- Origin: Started as a script the author wrote for personal use, later made public
- While publicly available, this is not a project that pursues user-friendliness

## Intended Users

This tool targets both engineers capable of analyzing communications at the
CAN log level and automotive users without a software engineering background.
Due to the nature of the data handled, active user support is not provided.

## Design Priorities

1. **Failing to read data that should be readable is not acceptable**
2. Within the bounds of (1), protocol compliance may be partially abandoned
3. Read-time optimization and usability improvements are low priorities

## Technical Premises

### Number of Attempts and Procedure

- Target DIDs: 3, candidate CAN IDs: 3, totaling `3 × 3 = 9` read attempts
- All attempts are executed **sequentially, without early termination, and
  deterministically**
- The tool never skips an attempt that might succeed

### Typical ECU Implementation

- A standard-compliant ECU typically responds on **only 1 CAN ID**
- Support for multiple CAN IDs (not required by the specification) is rare

### Typical Behavior

| Scenario | Result |
|---|---|
| Success | 3 of 9 attempts succeed / 6 fail |
| Failure | All 9 attempts fail |

### Failure Modes

1. No Response
2. Negative Response (NegRes)
3. Timeout after partial data reception

## Current State and Approach for NegRes Handling

### NegRes Other Than Pending

- **Approach**: No notification is shown to the user
- **Rationale**:
  - This response occurs frequently even during a successful run, so showing
    it would be noise and could mislead users
  - For failure analysis, the raw CAN log can be inspected via `--verbose`

### Pending (NRC 0x78)

- **Approach**: No notification is shown to the user
- **Implementation**:
  - Uses only a fixed timeout measured from the start of the read
    (default 10 seconds, configurable via option)
  - Does not implement the P2*_client timer reload upon receiving Pending as
    specified by UDS (ISO 14229); this is a deviation from the specification
- **Justification**:
  - Accurate implementation of the P2 family of timeouts is impractical in
    this tool's operating environment:
    - The exact timing parameters depend on the ECU implementation,
      and are not knowable from the tool's side
    - Latency between the application layer and the CAN controller (on the
      order of a few to tens of milliseconds, non-deterministic, for
      SLCAN/CAN adapters over USB) adds uncertainty to observed timestamps
  - By adopting a fixed value (10 seconds) longer than the specification
    default (P2*_client = 5 seconds), the design provides ample margin
    against the processing time on actual ECUs, thereby avoiding missed data