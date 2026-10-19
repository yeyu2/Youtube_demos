# Production Task Specification: Multi-Tenant Sliding Window Limiter

## 1. Objective
Implement a thread-safe, tenant-partitioned sliding-window rate limiter in Python.

## 2. Invariant Contracts (Enforced by Independent Auditor)
- **Invariant A (Strict Types):** `capacity` must be a positive integer; `window_seconds` must be a positive number. Invalid inputs must raise `ValueError` or `TypeError`.
- **Invariant B (Multi-Tenant Isolation):** Requests from `tenant-a` must never consume quota from `tenant-b`.
- **Invariant C (Time Boundary):** Timestamps older than `(now - window_seconds)` must be evicted.

## 3. Delivery Requirements
- Core Module: `src/rate_limiter.py`
- Test Suite: `tests/test_rate_limiter.py`
