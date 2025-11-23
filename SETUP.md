# Complete Setup Guide - Local K8s IDP for ECS Management

## Prerequisites

- Windows 10/11
- 8GB RAM minimum (16GB recommended)
- Docker Desktop installed
- Git installed
- AWS CLI configured with credentials

---

## Step 1: Install Required Tools

### 1.1 Install Chocolatey (if not installed)
```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
```

### 1.2 Install minikube and kubectl
```powershell
choco install minikube kubernetes-cli -y
```

### 1.3 Install Node.js (for Backstage)
```powershell
choco install nodejs-lts -y
```

### 1.4 Verify installations
```powershell
minikube version
kubectl version --client
node --version
npm --version
```

---

## Step 2: Start Local Kubernetes Cluster

### 2.1 Start minikube
```powershell
minikube start --driver=docker --cpus=4 --memory=8192
```

### 2.2 Verify cluster is running
```powershell
kubectl get nodes
kubectl cluster-info
```

You should see:
```
NAME       STATUS   ROLES           AGE   VERSION
minikube   Ready    control-plane   1m    v1.28.3
```

---

## Step 3: Deploy Backstage IDP

### 3.1 Create Backstage app
```powershell
cd D:\Projects\LEIDOS
npx @backstage/create-app@latest
# Name: ecs-platform
# Choose: SQLite (for simplicity)
```

### 3.2 Navigate to Backstage directory
```powershell
cd ecs-platform
```

### 3.3 Install dependencies
```powershell
npm install
```

### 3.4 Start Backstage locally (test)
```powershell
npm run dev
```

Open browser: http://localhost:3000

Press Ctrl+C to stop after verifying it works.

---

## Step 4: Configure AWS Credentials in Kubernetes

### 4.1 Create Kubernetes secret with AWS credentials
```powershell
kubectl create secret generic aws-credentials `
  --from-literal=AWS_ACCESS_KEY_ID=YOUR_ACCESS_KEY `
  --from-literal=AWS_SECRET_ACCESS_KEY=YOUR_SECRET_KEY `
  --from-literal=AWS_DEFAULT_REGION=us-east-1
```

### 4.2 Verify secret created
```powershell
kubectl get secrets
```

---

## Step 5: Deploy ECS Manager Service to Kubernetes

### 5.1 Apply Kubernetes manifests
```powershell
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/ecs-manager-deployment.yaml
kubectl apply -f k8s/ecs-manager-service.yaml
```

### 5.2 Verify deployment
```powershell
kubectl get pods -n ecs-platform
kubectl get services -n ecs-platform
```

### 5.3 Port forward to access service
```powershell
kubectl port-forward -n ecs-platform service/ecs-manager 8080:80
```

Test: http://localhost:8080

---

## Step 6: Setup GitHub Integration

### 6.1 Create GitHub Personal Access Token
1. Go to GitHub → Settings → Developer settings → Personal access tokens
2. Generate new token (classic)
3. Scopes: `repo`, `workflow`
4. Copy token

### 6.2 Store token in Kubernetes
```powershell
kubectl create secret generic github-token `
  --from-literal=GITHUB_TOKEN=ghp_YOUR_TOKEN_HERE `
  -n ecs-platform
```

### 6.3 Update GitHub repo in config
Edit `k8s/ecs-manager-deployment.yaml`:
```yaml
env:
  - name: GITHUB_REPO
    value: "YOUR_USERNAME/LEIDOS"
```

---

## Step 7: Deploy GitHub Actions Workflow

### 7.1 Create workflow file
Already created in `.github/workflows/ecs-gitops.yml`

### 7.2 Add AWS credentials to GitHub Secrets
1. Go to your repo → Settings → Secrets and variables → Actions
2. Add secrets:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`

### 7.3 Push to GitHub
```powershell
git add .
git commit -m "Add K8s IDP for ECS management"
git push origin ECS-Creation-Pipeline
```

---

## Step 8: Access the Platform

### 8.1 Get Backstage URL
```powershell
minikube service backstage -n ecs-platform --url
```

### 8.2 Get ECS Manager URL
```powershell
minikube service ecs-manager -n ecs-platform --url
```

### 8.3 Open in browser
- Backstage: http://localhost:3000
- ECS Manager: http://localhost:8080

---

## How It Works

### Creating an ECS Cluster

1. **User** opens Backstage GUI at http://localhost:3000
2. **User** fills form: cluster name, capacity provider, settings
3. **User** clicks "Create Cluster"
4. **Backstage** sends request to ECS Manager service in K8s
5. **ECS Manager** triggers GitHub webhook
6. **GitHub Actions** workflow starts
7. **GitHub Actions** commits cluster config to Git
8. **GitHub Actions** runs `terraform apply`
9. **Terraform** creates ECS cluster in AWS
10. **User** sees success message (2-5 minutes)

### Flow Diagram

```
User Browser
    ↓ (HTTP POST)
Backstage (K8s Pod)
    ↓ (HTTP POST)
ECS Manager (K8s Pod)
    ↓ (GitHub API)
GitHub Webhook
    ↓ (Trigger)
GitHub Actions
    ↓ (Git Commit)
Git Repository
    ↓ (Terraform Apply)
AWS ECS
```

---

## Monitoring

### Check Kubernetes Pods
```powershell
kubectl get pods -n ecs-platform -w
```

### Check Logs
```powershell
kubectl logs -f deployment/ecs-manager -n ecs-platform
kubectl logs -f deployment/backstage -n ecs-platform
```

### Check GitHub Actions
Go to: https://github.com/YOUR_USERNAME/LEIDOS/actions

---

## Troubleshooting

### Minikube won't start
```powershell
minikube delete
minikube start --driver=docker --cpus=4 --memory=8192
```

### Pods not running
```powershell
kubectl describe pod POD_NAME -n ecs-platform
kubectl logs POD_NAME -n ecs-platform
```

### Can't access services
```powershell
minikube tunnel
```

### AWS credentials not working
```powershell
kubectl delete secret aws-credentials
kubectl create secret generic aws-credentials --from-literal=...
kubectl rollout restart deployment/ecs-manager -n ecs-platform
```

---

## Cleanup

### Stop everything
```powershell
minikube stop
```

### Delete cluster
```powershell
minikube delete
```

### Remove Backstage
```powershell
cd D:\Projects\LEIDOS
Remove-Item -Recurse -Force ecs-platform
```

---

## Cost

- **Kubernetes (minikube)**: FREE (runs locally)
- **Backstage**: FREE (open source)
- **GitHub Actions**: FREE (2000 minutes/month)
- **AWS ECS Clusters**: FREE (empty clusters)
- **AWS ECS Tasks**: PAID (only when running containers)

**Total Platform Cost: $0/month**

---

## What You're Learning

1. **Kubernetes fundamentals** - Pods, Services, Deployments
2. **Platform Engineering** - Building internal developer platforms
3. **GitOps** - Infrastructure managed through Git
4. **CI/CD** - Automated pipelines with GitHub Actions
5. **Infrastructure as Code** - Terraform for AWS resources
6. **Microservices** - Service-to-service communication
7. **Cloud-native patterns** - Containers, orchestration, APIs

This is production-grade architecture used by companies like Spotify, Netflix, and Airbnb!
