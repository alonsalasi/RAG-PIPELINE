param(
    [Parameter(Mandatory=$true)]
    [string]$Username,
    [Parameter(Mandatory=$true)]
    [string]$Email,
    [Parameter(Mandatory=$true)]
    [string]$Password,
    [Parameter(Mandatory=$false)]
    [string]$Phone = "",
    [Parameter(Mandatory=$false)]
    [switch]$Permanent
)

$ErrorActionPreference = "Stop"

Write-Host "========================================"
Write-Host "  Cognito User Creation Tool"
Write-Host "========================================"
Write-Host ""

# Validate phone if provided
if ($Phone -and -not $Phone.StartsWith("+")) {
    Write-Host "ERROR: Phone must start with + (e.g., +972501234567)" -ForegroundColor Red
    exit 1
}

# Validate password
if ($Password.Length -lt 8) { Write-Host "ERROR: Password must be 8+ chars" -ForegroundColor Red; exit 1 }
if ($Password -notmatch '[A-Z]') { Write-Host "ERROR: Password needs uppercase" -ForegroundColor Red; exit 1 }
if ($Password -notmatch '[a-z]') { Write-Host "ERROR: Password needs lowercase" -ForegroundColor Red; exit 1 }
if ($Password -notmatch '[0-9]') { Write-Host "ERROR: Password needs number" -ForegroundColor Red; exit 1 }
if ($Password -notmatch '[^A-Za-z0-9]') { Write-Host "ERROR: Password needs symbol" -ForegroundColor Red; exit 1 }

# Get User Pool
Write-Host "Finding user pool..." -ForegroundColor Yellow
$pools = aws cognito-idp list-user-pools --max-results 60 --output json | ConvertFrom-Json
if (-not $pools.UserPools -or $pools.UserPools.Count -eq 0) {
    Write-Host "ERROR: No user pools found" -ForegroundColor Red
    exit 1
}

$userPoolId = $pools.UserPools[0].Id
Write-Host "Found: $($pools.UserPools[0].Name)" -ForegroundColor Green
Write-Host ""

# Build attributes array
$attrArgs = @(
    "Name=email,Value=$Email",
    "Name=email_verified,Value=true"
)
if ($Phone) {
    $attrArgs += "Name=phone_number,Value=$Phone"
    $attrArgs += "Name=phone_number_verified,Value=true"
}

# Create user
Write-Host "Creating user: $Username" -ForegroundColor Yellow
$ErrorActionPreference = "Continue"
$output = & aws cognito-idp admin-create-user --user-pool-id $userPoolId --username $Username --temporary-password $Password --user-attributes $attrArgs 2>&1 | Out-String
$ErrorActionPreference = "Stop"

if ($output -match '"Username"' -or $LASTEXITCODE -eq 0) {
    Write-Host "User created!" -ForegroundColor Green
} else {
    Write-Host "ERROR: Failed to create user" -ForegroundColor Red
    Write-Host $output -ForegroundColor Red
    exit 1
}

# Set permanent password if requested
if ($Permanent) {
    Write-Host "Setting permanent password..." -ForegroundColor Yellow
    aws cognito-idp admin-set-user-password --user-pool-id $userPoolId --username "$Username" --password "$Password" --permanent | Out-Null
}

# Enable MFA (user still needs to set up authenticator on first login)
Write-Host "Enabling MFA requirement..." -ForegroundColor Yellow
try {
    aws cognito-idp admin-set-user-mfa-preference --user-pool-id $userPoolId --username "$Username" --software-token-mfa-settings Enabled=true,PreferredMfa=false 2>&1 | Out-Null
    Write-Host "MFA enabled (user must configure authenticator on first login)" -ForegroundColor Green
} catch {
    Write-Host "Note: MFA will be enabled after user sets up authenticator" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Login credentials:" -ForegroundColor Cyan
Write-Host "  Username: $Username"
Write-Host "  Email: $Email"
if ($Phone) { Write-Host "  Phone: $Phone" }
Write-Host "  Password: $Password"
if ($Permanent) {
    Write-Host "  (Can login immediately)" -ForegroundColor Green
} else {
    Write-Host "  (Must change password on first login)" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Note: User must enable MFA on first login" -ForegroundColor Yellow

Write-Host ""
Write-Host "========================================"
Write-Host "  SUCCESS!"
Write-Host "========================================"
