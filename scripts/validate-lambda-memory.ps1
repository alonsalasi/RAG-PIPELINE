# Lambda Memory Usage Profiler
$ErrorActionPreference = "Stop"

$PROJECT_NAME = "pdfquery"
$REGION = "us-east-1"

Write-Host "Lambda Memory Usage Report" -ForegroundColor Cyan
Write-Host "=========================" -ForegroundColor Cyan
Write-Host ""

$functions = @(
    "$PROJECT_NAME-agent-executor",
    "$PROJECT_NAME-ingestion-worker"
)

foreach ($func in $functions) {
    Write-Host "Function: $func" -ForegroundColor Yellow
    
    $config = aws lambda get-function-configuration --function-name $func --region $REGION | ConvertFrom-Json
    $allocatedMB = $config.MemorySize
    
    Write-Host "  Allocated: $allocatedMB MB" -ForegroundColor Gray
    
    # Get recent invocations
    $logs = aws logs filter-log-events `
        --log-group-name "/aws/lambda/$func" `
        --filter-pattern "Max Memory Used" `
        --max-items 10 `
        --region $REGION 2>$null | ConvertFrom-Json
    
    if ($logs.events.Count -gt 0) {
        $memoryUsages = @()
        foreach ($event in $logs.events) {
            if ($event.message -match "Max Memory Used: (\d+) MB") {
                $memoryUsages += [int]$matches[1]
            }
        }
        
        if ($memoryUsages.Count -gt 0) {
            $avgUsed = ($memoryUsages | Measure-Object -Average).Average
            $maxUsed = ($memoryUsages | Measure-Object -Maximum).Maximum
            $utilization = [math]::Round(($avgUsed / $allocatedMB) * 100, 1)
            
            Write-Host "  Avg Used: $([math]::Round($avgUsed, 0)) MB" -ForegroundColor Gray
            Write-Host "  Max Used: $maxUsed MB" -ForegroundColor Gray
            Write-Host "  Utilization: $utilization%" -ForegroundColor $(if ($utilization -lt 50) { "Yellow" } else { "Green" })
            
            if ($utilization -lt 50) {
                $recommended = [math]::Ceiling($maxUsed * 1.2 / 128) * 128
                Write-Host "  Recommendation: Reduce to $recommended MB" -ForegroundColor Cyan
            }
        } else {
            Write-Host "  No memory metrics found" -ForegroundColor Gray
        }
    } else {
        Write-Host "  No recent invocations" -ForegroundColor Gray
    }
    
    Write-Host ""
}
