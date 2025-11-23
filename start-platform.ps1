# ECS Platform Startup Script
# Starts minikube and deploys the K8s platform

Write-Host "Starting ECS Platform..." -ForegroundColor Green

# Check if minikube is running
Write-Host "`nChecking minikube status..." -ForegroundColor Cyan
$minikubeStatus = minikube status 2>$null

if ($LASTEXITCODE -ne 0) {
    Write-Host "Minikube is not running. Starting minikube..." -ForegroundColor Yellow
    minikube start --driver=docker
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to start minikube" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "Minikube is already running" -ForegroundColor Green
}

# Check if namespace exists
Write-Host "`nChecking namespace..." -ForegroundColor Cyan
$namespaceExists = kubectl get namespace ecs-platform 2>$null

if ($LASTEXITCODE -ne 0) {
    Write-Host "Namespace does not exist. Creating..." -ForegroundColor Yellow
    kubectl apply -f k8s/namespace.yaml
} else {
    Write-Host "Namespace exists" -ForegroundColor Green
}

# Check if secrets exist
Write-Host "`nChecking secrets..." -ForegroundColor Cyan
$secretsExist = kubectl get secret aws-credentials -n ecs-platform 2>$null

if ($LASTEXITCODE -ne 0) {
    Write-Host "Secrets not found! Please create secrets first:" -ForegroundColor Red
    Write-Host "Run the commands from WINDOWS-SETUP.md to create secrets" -ForegroundColor Yellow
    exit 1
} else {
    Write-Host "Secrets configured" -ForegroundColor Green
}

# Deploy platform
Write-Host "`nDeploying platform components..." -ForegroundColor Cyan
kubectl apply -f k8s/ecs-manager-configmap.yaml
kubectl apply -f k8s/ecs-manager-deployment.yaml
kubectl apply -f k8s/ecs-manager-service.yaml

# Wait for pod to be ready
Write-Host "`nWaiting for pod to be ready..." -ForegroundColor Cyan
kubectl wait --for=condition=ready pod -l app=ecs-manager -n ecs-platform --timeout=120s

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nPlatform is ready!" -ForegroundColor Green
    Write-Host "`nStarting port-forward in background..." -ForegroundColor Cyan
    Start-Job -ScriptBlock { kubectl port-forward -n ecs-platform svc/ecs-manager 8080:8080 } | Out-Null
    Start-Sleep -Seconds 2
    Write-Host "`nAccess the platform at: http://localhost:8080" -ForegroundColor Cyan
    Write-Host "`nUseful commands:" -ForegroundColor Yellow
    Write-Host "  kubectl get pods -n ecs-platform" -ForegroundColor White
    Write-Host "  kubectl logs -f deployment/ecs-manager -n ecs-platform" -ForegroundColor White
    Write-Host "  Get-Job | Stop-Job (to stop port-forward)" -ForegroundColor White
} else {
    Write-Host "`nFailed to start platform" -ForegroundColor Red
    Write-Host "Check logs with: kubectl logs -f deployment/ecs-manager -n ecs-platform" -ForegroundColor Yellow
    exit 1
}
