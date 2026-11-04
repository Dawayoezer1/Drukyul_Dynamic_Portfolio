$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $chosenVersion = $null
        foreach ($candidate in @('-3.13','-3.12','-3.11')) {
            & py $candidate -c 'import sys; sys.exit(0)' 2>$null
            if ($LASTEXITCODE -eq 0) { $chosenVersion = $candidate; break }
        }
        if ($chosenVersion) { & py $chosenVersion -m venv .venv }
        else { & py -3 -m venv .venv }
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv .venv
    } else {
        throw 'Install Python 3.11 or newer from python.org. Select Add Python to PATH, then run START_APP.bat again.'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
$requirementsPath = Join-Path $PSScriptRoot 'requirements.txt'
$requirementsHash = (Get-FileHash -LiteralPath $requirementsPath -Algorithm SHA256).Hash
$stampPath = Join-Path $PSScriptRoot '.venv\drukyul-requirements.sha256'
$installedHash = if (Test-Path -LiteralPath $stampPath) { (Get-Content -LiteralPath $stampPath -Raw).Trim() } else { '' }
if ($installedHash -ne $requirementsHash) {
    Write-Host 'Installing required packages. First launch may take a few minutes.' -ForegroundColor Cyan
    & $pythonPath -m pip install -r $requirementsPath
    if ($LASTEXITCODE -ne 0) { throw 'Installation failed. Check internet access. Python 3.11-3.13 is recommended.' }
    Set-Content -LiteralPath $stampPath -Value $requirementsHash
}
Write-Host ''
Write-Host 'Drukyul: http://localhost:8501' -ForegroundColor Green
Write-Host 'Keep this window open. Press Ctrl+C here to stop.' -ForegroundColor Cyan
Write-Host 'Free Yahoo Finance is the default. No API key needed. Keep internet connected.'
# The local browser opens only once the server reports healthy; avoids the public IP timeout.
$browserJob = Start-Job -ScriptBlock {
    for ($attempt = 0; $attempt -lt 90; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8501/_stcore/health' -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                Start-Process 'http://localhost:8501'
                return
            }
        } catch { }
        Start-Sleep -Seconds 1
    }
}
try {
    & $pythonPath -m streamlit run app.py --server.address=127.0.0.1 --server.port=8501 --server.headless=true --browser.gatherUsageStats=false
    if ($LASTEXITCODE -ne 0) { throw 'Dashboard stopped with an error. If port 8501 is in use, close the earlier Drukyul window and try again.' }
} finally {
    Stop-Job $browserJob -ErrorAction SilentlyContinue
    Remove-Job $browserJob -Force -ErrorAction SilentlyContinue
}
