# Windows Setup Guide - Local K8s IDP for ECS Management

## Prerequisites

- Windows 10/11
- 8GB RAM minimum (16GB recommended)
- Docker Desktop installed and running
- Git installed
- AWS CLI configured

---

## Step 1: Install Required Tools (PowerShell as Admin)

### 1.1 Install Chocolatey
```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
```

### 1.2 Install minikube and kubectl
```powershell
choco install minikube kubernetes-cli -y
```

### 1.3 Verify installations
```powershell
minikube version
kubectl version --client
```

---

## Step 2: Start Local Kubernetes Cluster

### 2.1 Start minikube
```powershell
minikube start --driver=docker --cpus=4 --memory=8192
```

### 2.2 Verify cluster
```powershell
kubectl get nodes
kubectl cluster-info
```

---

## Step 3: Configure AWS Credentials in Kubernetes

### 3.1 Create AWS credentials secret
```powershell
kubectl create secret generic aws-credentials `
  --from-literal=AWS_ACCESS_KEY_ID=YOUR_ACCESS_KEY_HERE `
  --from-literal=AWS_SECRET_ACCESS_KEY=YOUR_SECRET_KEY_HERE `
  --from-literal=AWS_DEFAULT_REGION=us-east-1
```

### 3.2 Verify secret
```powershell
kubectl get secrets
```

---

## Step 4: Setup GitHub Integration

### 4.1 Create GitHub Personal Access Token
1. Go to GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Click "Generate new token (classic)"
3. Name: `K8s-Platform-Token`
4. Scopes: Check `repo` and `workflow`
5. Click "Generate token"
6. **Copy the token**

### 4.2 Create GitHub token secret
```powershell
kubectl create secret generic github-token `
  --from-literal=GITHUB_TOKEN=ghp_YOUR_TOKEN_HERE `
  -n ecs-platform
```

### 4.3 Update GitHub repo in deployment
Edit `k8s\ecs-manager-deployment.yaml` line 24:
```yaml
- name: GITHUB_REPO
  value: "YOUR_USERNAME/LEIDOS"  # Change this to your repo
```

---

## Step 5: Add AWS Credentials to GitHub Secrets

1. Go to your GitHub repo → Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Add these secrets:
   - Name: `AWS_ACCESS_KEY_ID`, Value: Your AWS access key
   - Name: `AWS_SECRET_ACCESS_KEY`, Value: Your AWS secret key

---

## Step 6: Deploy Platform to Kubernetes

### 6.1 Create namespace
```powershell
kubectl apply -f k8s\namespace.yaml
```

### 6.2 Deploy ConfigMap (code)
```powershell
kubectl apply -f k8s\ecs-manager-configmap.yaml
```

### 6.3 Deploy application
```powershell
kubectl apply -f k8s\ecs-manager-deployment.yaml
```

### 6.4 Deploy service
```powershell
kubectl apply -f k8s\ecs-manager-service.yaml
```

### 6.5 Verify deployment
```powershell
kubectl get pods -n ecs-platform
kubectl get services -n ecs-platform
```

Wait until pod status is "Running".

---

## Step 7: Access the Platform

### 7.1 Get the service URL
```powershell
minikube service ecs-manager -n ecs-platform --url
```

This will output something like: `http://127.0.0.1:XXXXX`

### 7.2 Open in browser
Copy the URL and open in your browser.

You should see the ECS Manager GUI!

---

## Step 8: Push to GitHub

### 8.1 Stage all files
```powershell
git add .
```

### 8.2 Commit
```powershell
git commit -m "Add K8s platform for ECS management"
```

### 8.3 Push to GitHub
```powershell
git push origin ECS-Creation-Pipeline
```

---

## Step 9: Test the Platform

### 9.1 Create a test cluster
1. Open the GUI in browser
2. Enter cluster name: `test-cluster`
3. Select capacity provider: `FARGATE`
4. Click "Create Cluster (via GitOps)"

### 9.2 Monitor progress
```powershell
# Watch GitHub Actions
# Go to: https://github.com/YOUR_USERNAME/LEIDOS/actions

# Watch pod logs
kubectl logs -f deployment/ecs-manager -n ecs-platform
```

### 9.3 Verify cluster created (after 2-5 minutes)
```powershell
aws ecs list-clusters
aws ecs describe-clusters --clusters test-cluster
```

---

## Monitoring Commands

### Check pod status
```powershell
kubectl get pods -n ecs-platform
```

### View pod logs
```powershell
kubectl logs -f deployment/ecs-manager -n ecs-platform
```

### Check service
```powershell
kubectl get services -n ecs-platform
```

### Describe pod (for troubleshooting)
```powershell
kubectl describe pod -n ecs-platform
```

### Restart deployment
```powershell
kubectl rollout restart deployment/ecs-manager -n ecs-platform
```

---

## Troubleshooting

### Minikube won't start
```powershell
minikube delete
minikube start --driver=docker --cpus=4 --memory=8192
```

### Pod not running
```powershell
kubectl describe pod -n ecs-platform
kubectl logs deployment/ecs-manager -n ecs-platform
```

### Can't access service
```powershell
# Try tunnel mode
minikube tunnel
```

Then access at: http://localhost:30080

### AWS credentials not working
```powershell
# Delete and recreate secret
kubectl delete secret aws-credentials
kubectl create secret generic aws-credentials `
  --from-literal=AWS_ACCESS_KEY_ID=YOUR_KEY `
  --from-literal=AWS_SECRET_ACCESS_KEY=YOUR_SECRET `
  --from-literal=AWS_DEFAULT_REGION=us-east-1

# Restart pod
kubectl rollout restart deployment/ecs-manager -n ecs-platform
```

### GitHub webhook not triggering
1. Check GitHub token is valid
2. Check repo name is correct in deployment
3. Check GitHub Actions tab for errors

---

## Cleanup

### Stop minikube
```powershell
minikube stop
```

### Delete cluster
```powershell
minikube delete
```

### Delete all resources
```powershell
kubectl delete namespace ecs-platform
```

---

## Quick Reference

### Start platform
```powershell
minikube start
kubectl get pods -n ecs-platform
minikube service ecs-manager -n ecs-platform --url
```

### Stop platform
```powershell
minikube stop
```

### View logs
```powershell
kubectl logs -f deployment/ecs-manager -n ecs-platform
```

### Restart service
```powershell
kubectl rollout restart deployment/ecs-manager -n ecs-platform
```

### Check AWS clusters
```powershell
aws ecs list-clusters
```

---

## Cost

- **Kubernetes (minikube)**: FREE
- **GitHub Actions**: FREE (2000 min/month)
- **AWS ECS Clusters**: FREE (empty)
- **AWS ECS Tasks**: PAID (only when running)

**Total: $0/month**

---

## Next Steps

1. Read `HOW-IT-WORKS.md` to understand the architecture
2. Create test clusters via the GUI
3. Monitor GitHub Actions workflows
4. Check Git commits to see GitOps in action
5. Verify clusters in AWS Console

You now have a production-grade platform engineering setup running locally!
