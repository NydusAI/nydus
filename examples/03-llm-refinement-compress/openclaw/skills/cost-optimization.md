When performing a cost optimization analysis, start by asking the user
for their current monthly bill or an estimate of their cloud spending.
If they don't have exact numbers, ask them to describe their
infrastructure: how many instances, what sizes, which managed services,
and what their traffic patterns look like.

Work through these categories systematically:

1. Compute right-sizing: Check if instances are over-provisioned by
   looking at CPU and memory utilization. If average utilization is
   below 30%, recommend downsizing. If utilization is spiky, recommend
   auto-scaling instead of running at peak capacity 24/7.

2. Pricing model: Are they using on-demand pricing for predictable
   workloads? If a workload runs consistently for more than 8 hours a
   day, Savings Plans or Reserved Instances almost always save money.
   Walk through the commitment trade-offs.

3. Storage: Check for unused EBS volumes, old snapshots, and S3
   buckets without lifecycle policies. These are common sources of
   waste that accumulate over time.

4. Data transfer: Cross-region and cross-AZ transfer costs add up
   quickly. If services communicate frequently across AZs, consider
   co-locating them. For cross-region, evaluate whether a CDN or
   regional deployment would reduce transfer costs.

5. Managed services: Sometimes a managed service costs more than
   self-hosting, but saves enough engineering time to be worth it.
   Evaluate total cost of ownership, not just the bill.

Present findings with estimated savings per category. Always note the
trade-offs — cheaper isn't always better if it introduces risk or
operational burden.
