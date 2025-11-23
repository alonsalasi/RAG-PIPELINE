# ECS Creation Pipeline (Practice Branch)

Complete Platform Engineering setup with Kubernetes IDP for managing AWS ECS clusters.

## Architecture

```
Local Kubernetes (minikube)
    ↓
Backstage IDP (GUI)
    ↓
GitHub Webhook
    ↓
GitHub Actions (CI/CD)
    ↓
Terraform
    ↓
AWS ECS Clusters
```

## Components

1. **Local Kubernetes** - Free tier IDP platform (minikube)
2. **Backstage** - Open-source developer portal with GUI
3. **GitHub Actions** - CI/CD pipeline
4. **Terraform** - Infrastructure as Code
5. **AWS ECS** - Container orchestration

## Setup Instructions

See `SETUP.md` for complete installation guide.

## What You'll Learn

- Platform Engineering fundamentals
- Kubernetes basics
- GitOps workflows
- CI/CD pipelines
- Infrastructure as Code
- Self-service platforms
