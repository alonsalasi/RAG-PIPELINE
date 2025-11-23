# ECS Platform Shutdown Script
# Stops the platform but keeps minikube running

Write-Host "🛑 Stopping ECS Platform..." -ForegroundColor Yellow

# Delete platform resources
Write-Host "`n📦 Removing platform components..." -ForegroundColor Cyan
kubectl delete -f k8s/ecs-manager-service.yaml 2>$null
kubectl delete -f k8s/ecs-manager-deployment.yaml 2>$null
kubectl delete -f k8s/ecs-manager-configmap.yaml 2>$null

Write-Host "`n✅ Platform stopped (minikube still running)" -ForegroundColor Green
Write-Host "`nTo stop minikube: minikube stop" -ForegroundColor Yellow
Write-Host "To delete everything: minikube delete" -ForegroundColor Yellow
