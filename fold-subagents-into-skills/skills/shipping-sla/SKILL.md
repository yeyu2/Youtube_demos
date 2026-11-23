---
name: shipping-sla
description: Verify carrier SLA windows, regional warehouse cutoffs, and delivery exception dates before issuing shipping refunds or item exchanges.
---

# Shipping SLA & Cutoff Rules

1. Never refund from `lookup_order()` alone: always call `check_carrier_sla(order_id, carrier, ship_date)` before `issue_refund()` or `create_exchange()`.
2. Standard ground orders have a 72-hour `carrier_sla_hours` window; weather or customs exceptions add 48 hours.
3. Same-day exchanges require `local_warehouse_hour < 16` in the destination region.
