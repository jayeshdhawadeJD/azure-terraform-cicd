# scripts/Get-CostData.ps1

$subscriptionId = "bb8f8c0b-6d1b-4593-882b-d9f264692833"
$bodyFile = "cost-query.json"
$outputFile = "cost-data-$(Get-Date -Format 'yyyy-MM-dd').json"
$storageAccount = "stportfoliodemo01"
$containerName = "demo-list"

$maxRetries = 5
$attempt = 0
$result = $null

while ($attempt -lt $maxRetries -and $null -eq $result) {
  $attempt++
  Write-Host "Attempt $attempt of $maxRetries..."

  $response = az rest --method post `
    --url "https://management.azure.com/subscriptions/$subscriptionId/providers/Microsoft.CostManagement/query?api-version=2023-11-01" `
    --body "@$bodyFile" 2>&1
  $exit = $LASTEXITCODE

  if ($exit -eq 0) {
    $result = ($response | Out-String) | ConvertFrom-Json
  } else {
    $errorText = ($response | Out-String).Trim()
    Write-Host "Request failed with exit code $exit."
    Write-Host "----- error details -----"
    Write-Host $errorText
    Write-Host "-------------------------"
    Start-Sleep -Seconds ($attempt * 30)
  }
}

if ($null -eq $result) {
  throw "Failed to get cost data after $maxRetries attempts"
}

$costData = @{
  date       = (Get-Date -Format "yyyy-MM-dd")
  resources  = $result.properties.rows | ForEach-Object {
    @{
      resourceId = $_[1]
      cost       = [math]::Round($_[0], 4)
      currency   = $_[2]
    }
  }
}

$costData | ConvertTo-Json -Depth 3 | Out-File $outputFile -Encoding utf8
Write-Host "Saved to $outputFile"

az storage blob upload `
  --account-name $storageAccount `
  --container-name $containerName `
  --name $outputFile `
  --file $outputFile `
  --auth-mode login

Write-Host "Uploaded to $containerName/$outputFile"