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

## Approach for NegRes Handling

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


# Functional → physical transition for multi-frame UDS

`edr-data-reader` is a UDS **tester** that reads DIDs from an ECU per
GB39732-2020. Its isotp topology looks structurally awkward, but the
shape is the only way to satisfy the standard's required communication
pattern with the abstractions
[`python-can-isotp`](https://github.com/pylessard/python-can-isotp)
exposes. This note records the constraint so the structure is not
"cleaned up" later in a way that breaks the protocol.

## The protocol flow

GB39732-2020 documents the EDR DID Read as a functional → physical
transition, and ISO 15765-2 forbids multi-frame transfers on functional
addresses, so the response must use the responding ECU's physical pair:

```
Tester (edr-data-reader) -> ECU   SF   functional addr   (request)
Tester                   <- ECU   FF   physical addr     (response start)
Tester                   -> ECU   FC   physical addr     (flow control)
Tester                   <- ECU   CF   physical addr     ...
```

## The key constraint

**When the tester emits the broadcast request, it does not yet know
which ECU will respond — and therefore does not know which physical
arbitration ID the FF and subsequent FC / CFs will use.** The receive
mechanism must be configured *before* the FF arrives; it cannot be wired
up afterwards.

`isotp.Address` binds one session to one fixed `(tx_id, rx_id)` pair for
its lifetime, and `AsymmetricAddress` fixes the two schemes statically.
Neither defers the binding to FF-arrival time.

## How the tester copes

The tester pre-allocates a *bank* of full physical-pair stacks covering
every plausible responder; each stack's `txid` is what the tester uses
to send FC back to *that specific* ECU once the FF identifies who
replied. A separate emit-only stack performs the functional broadcast
send.

[`udsoncan`](https://github.com/pylessard/python-udsoncan) was
considered but builds on the same single-pipe abstraction, so it does
not close the gap.

## Upstream

[Issue #33 (Functional Message Support for Server)](https://github.com/pylessard/python-can-isotp/issues/33)
covers both sides of this gap; the maintainer notes that emitting Flow
Control on a CAN ID different from the receive side is not natively
supported.
