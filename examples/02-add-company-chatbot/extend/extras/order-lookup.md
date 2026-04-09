# Order Lookup

Given a customer email or order ID (format: ORD-XXXXXXXX), query the
order database and return:
- Order status: pending / shipped / delivered / returned
- Tracking number and carrier
- Estimated delivery date
- Line items with quantities and amounts

Use the ORDER_DB credential for read-only database access. Format
results as a short summary, not raw JSON. If the order is not found,
ask the customer to double-check the order ID.
