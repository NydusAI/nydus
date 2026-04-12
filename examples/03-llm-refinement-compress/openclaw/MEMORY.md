# Cloud Provider Reference

## AWS Compute

When users ask about compute on AWS, the primary options are EC2 for
full VM control, ECS or EKS for container orchestration, and Lambda for
event-driven serverless workloads. EC2 is the right choice when the
workload needs specific instance types, GPU access, or long-running
processes that exceed Lambda's 15-minute timeout. ECS is appropriate for
teams already using Docker who want AWS-native orchestration without
managing the Kubernetes control plane. EKS is the better choice when the
team has Kubernetes expertise or needs multi-cloud portability since
Kubernetes configs transfer across providers. Lambda works best for
short-lived, event-triggered functions with unpredictable traffic
patterns where paying per invocation beats paying for idle capacity.

## GCP Compute

On Google Cloud, the equivalent options are Compute Engine for VMs,
Cloud Run for managed containers, GKE for Kubernetes, and Cloud
Functions for serverless. Cloud Run is notably simpler than ECS: it
auto-scales to zero, which makes it excellent for internal tools and
APIs with bursty traffic. GKE Autopilot removes most of the node
management overhead that makes EKS painful for small teams.

## Azure Compute

Azure's compute lineup includes Virtual Machines, Azure Container
Apps, AKS, and Azure Functions. Container Apps is Azure's answer to
Cloud Run: managed containers with scale-to-zero. AKS has improved
significantly in the last two years but still requires more operational
effort than GKE Autopilot for equivalent workloads.

## Cross-Provider Notes

- For most teams: start with managed containers (Cloud Run, Container
  Apps, or ECS with Fargate). Move to Kubernetes only when you need
  the orchestration features.
- GPU workloads: AWS has the best GPU instance variety. GCP has better
  pricing for sustained use. Azure is competitive for ML workloads
  via Azure ML.
- Serverless: Lambda has the largest ecosystem. Cloud Functions is
  catching up. Azure Functions has the best .NET integration.
