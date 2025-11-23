# How the K8s Platform Works

## Complete Flow Explanation

### 1. Local Kubernetes Cluster (minikube)

**What it is:** A single-node Kubernetes cluster running on your Windows machine using Docker.

**Why:** Provides a free, local platform to run services without needing cloud infrastructure.

**Components:**
- **Control Plane:** Manages the cluster (API server, scheduler, controller)
- **Worker Node:** Runs your application pods
- **Docker:** Container runtime

```
Your Windows PC
    ↓
Docker Desktop
    ↓
minikube (Kubernetes)
    ↓
Pods (ECS Manager, Backstage)
```

---

### 2. ECS Manager Service (Running in K8s)

**What it is:** A Python web server running as a Kubernetes pod.

**Files:**
- `k8s/ecs-manager-deployment.yaml` - Defines how to run the pod
- `k8s/ecs-manager-service.yaml` - Exposes the pod on port 30080
- `k8s/ecs-manager-configmap.yaml` - Contains the Python code and HTML

**What it does:**
1. Serves HTML GUI at http://localhost:30080
2. Receives API requests from the GUI
3. Triggers GitHub webhooks
4. Uses AWS credentials from Kubernetes secrets

**Code breakdown:**
```python
# server.py (simplified)
class ECSManagerHandler:
    def do_POST(self):
        # Get cluster details from request
        data = json.loads(body)
        
        # Trigger GitHub Actions via webhook
        requests.post(
            'https://api.github.com/repos/YOUR_REPO/dispatches',
            headers={'Authorization': f'token {GITHUB_TOKEN}'},
            json={'event_type': 'create-ecs-cluster', 'client_payload': data}
        )
```

---

### 3. GitHub Webhook Flow

**Step 1:** User clicks "Create Cluster" in GUI

**Step 2:** Browser sends POST to http://localhost:30080/api/ecs/create
```json
{
  "clusterName": "my-cluster",
  "capacityProvider": "FARGATE",
  "containerInsights": "disabled"
}
```

**Step 3:** ECS Manager pod receives request

**Step 4:** ECS Manager calls GitHub API
```bash
POST https://api.github.com/repos/YOUR_USERNAME/LEIDOS/dispatches
Authorization: token ghp_YOUR_TOKEN
{
  "event_type": "create-ecs-cluster",
  "client_payload": {
    "clusterName": "my-cluster",
    "capacityProvider": "FARGATE",
    "containerInsights": "disabled",
    "user": "k8s-platform"
  }
}
```

**Step 5:** GitHub receives webhook and triggers Actions workflow

---

### 4. GitHub Actions Workflow

**File:** `.github/workflows/ecs-gitops.yml`

**Trigger:**
```yaml
on:
  repository_dispatch:
    types: [create-ecs-cluster, delete-ecs-cluster]
```

**Steps:**

**Step 1: Checkout code**
```yaml
- uses: actions/checkout@v3
```
Downloads your Git repository to the GitHub Actions runner.

**Step 2: Setup Terraform**
```yaml
- uses: hashicorp/setup-terraform@v2
```
Installs Terraform CLI.

**Step 3: Configure AWS**
```yaml
- uses: aws-actions/configure-aws-credentials@v2
  with:
    aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
    aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
```
Sets up AWS credentials from GitHub Secrets.

**Step 4: Create Cluster Config**
```bash
cat >> ecs-clusters.tf << EOF
resource "aws_ecs_cluster" "cluster_my_cluster" {
  cluster_name = "my-cluster"
  capacity_providers = ["FARGATE"]
  ...
}
EOF
```
Appends Terraform code to `ecs-clusters.tf`.

**Step 5: Commit to Git**
```bash
git add ecs-clusters.tf
git commit -m "K8s Platform: Create ECS cluster my-cluster"
git push
```
Commits the new cluster configuration to Git.

**Step 6: Terraform Apply**
```bash
terraform init
terraform apply -auto-approve
```
Creates the actual ECS cluster in AWS.

---

### 5. Terraform Creates ECS Cluster

**What happens:**

1. Terraform reads `ecs-clusters.tf`
2. Terraform calls AWS ECS API
3. AWS creates the cluster
4. Terraform stores state

**AWS API calls made:**
```
CreateCluster(
  clusterName="my-cluster",
  capacityProviders=["FARGATE"],
  settings=[{name: "containerInsights", value: "disabled"}]
)
```

**Result:** ECS cluster exists in your AWS account!

---

### 6. Kubernetes Secrets (Security)

**AWS Credentials:**
```bash
kubectl create secret generic aws-credentials \
  --from-literal=AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE \
  --from-literal=AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY \
  --from-literal=AWS_DEFAULT_REGION=us-east-1
```

**GitHub Token:**
```bash
kubectl create secret generic github-token \
  --from-literal=GITHUB_TOKEN=ghp_YOUR_TOKEN_HERE
```

**How it's used:**
```yaml
# In deployment.yaml
env:
- name: AWS_ACCESS_KEY_ID
  valueFrom:
    secretKeyRef:
      name: aws-credentials
      key: AWS_ACCESS_KEY_ID
```

Kubernetes injects these as environment variables into the pod.

---

### 7. Complete End-to-End Flow

```
1. User opens browser → http://localhost:30080
2. User fills form: cluster name, capacity provider
3. User clicks "Create Cluster"
4. Browser → POST /api/ecs/create → ECS Manager Pod (K8s)
5. ECS Manager Pod → GitHub API webhook
6. GitHub → Triggers Actions workflow
7. GitHub Actions → Commits cluster to Git
8. GitHub Actions → Runs terraform apply
9. Terraform → Calls AWS ECS API
10. AWS → Creates ECS cluster
11. User sees success message (2-5 minutes total)
```

---

### 8. Why This Architecture?

**Local K8s (minikube):**
- ✅ Free (no cloud costs)
- ✅ Learn Kubernetes
- ✅ Production-like environment
- ✅ Can run multiple services

**GitOps (Git + CI/CD):**
- ✅ Audit trail (every change in Git)
- ✅ Rollback capability (revert commits)
- ✅ Approval process (pull requests)
- ✅ Infrastructure as Code

**Terraform:**
- ✅ Declarative (describe what you want)
- ✅ State management (knows what exists)
- ✅ Idempotent (safe to run multiple times)
- ✅ Multi-cloud (works with AWS, GCP, Azure)

---

### 9. Monitoring & Debugging

**Check if pods are running:**
```powershell
kubectl get pods -n ecs-platform
```

**View pod logs:**
```powershell
kubectl logs -f deployment/ecs-manager -n ecs-platform
```

**Check GitHub Actions:**
Go to: https://github.com/YOUR_USERNAME/LEIDOS/actions

**Check AWS ECS:**
```powershell
aws ecs list-clusters
aws ecs describe-clusters --clusters my-cluster
```

---

### 10. What You're Learning

**Kubernetes Concepts:**
- Pods (smallest deployable unit)
- Deployments (manages pods)
- Services (exposes pods)
- ConfigMaps (configuration data)
- Secrets (sensitive data)
- Namespaces (isolation)

**Platform Engineering:**
- Self-service portals
- Abstraction layers
- Developer experience
- Golden paths

**GitOps:**
- Infrastructure as Code
- Git as source of truth
- Automated pipelines
- Declarative configuration

**Cloud Native:**
- Containers
- Orchestration
- Microservices
- API-driven

This is the same architecture used by:
- **Spotify** (Backstage)
- **Netflix** (Spinnaker)
- **Weaveworks** (FluxCD)
- **Argo** (ArgoCD)

You're learning production-grade platform engineering!
