# LSM Bridge for HolonOS

This directory contains a bridge that allows KarmazynOS to answer access control queries from the `holo_lsm` Linux Security Module.

## How it works

1. `holo_lsm` intercepts file operations on inodes marked with `security.hss.lock`.
2. It sends a `hss_upcall_msg` structure to a Unix socket (`/run/hss-daemon.sock`).
3. `hss_bridge.py` listens on this socket, forwards the request to KarmazynOS.
4. KarmazynOS evaluates the context (`phi_context`, agent ID, policy) and returns a decision.
5. The bridge sends a `hss_upcall_resp` back to the kernel, which enforces it.

## Requirements

- Linux kernel with `holo_lsm` loaded.
- Python 3.10+ with `karmazyn.py` and `numpy`.

## Usage

```bash
sudo python hss_bridge.py
