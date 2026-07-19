[CmdletBinding()]
param(
    [int]$Port = 5061,
    [string]$Executable = "dist/PDFeditorAthome.exe"
)

$ErrorActionPreference = "Stop"
$resolvedExecutable = (Resolve-Path -LiteralPath $Executable).Path
$previousPort = $env:PDFEDITORATHOME_PORT
$previousNoBrowser = $env:PDFEDITORATHOME_NO_BROWSER
$process = $null

try {
    $env:PDFEDITORATHOME_PORT = $Port.ToString()
    $env:PDFEDITORATHOME_NO_BROWSER = "1"
    $process = Start-Process -FilePath $resolvedExecutable -PassThru -WindowStyle Hidden

    $healthUri = "http://127.0.0.1:$Port/api/health"
    $homeUri = "http://127.0.0.1:$Port/"
    $deadline = (Get-Date).AddSeconds(30)
    do {
        try {
            $health = Invoke-RestMethod -Uri $healthUri -TimeoutSec 2
            if ($health.status -eq "ok") {
                break
            }
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    } while ((Get-Date) -lt $deadline)

    if ($null -eq $health -or $health.status -ne "ok") {
        throw "The packaged application did not become healthy within 30 seconds."
    }

    $homeResponse = Invoke-WebRequest -Uri $homeUri -UseBasicParsing -TimeoutSec 5
    if ($homeResponse.StatusCode -ne 200 -or $homeResponse.Content -notmatch "PDFeditorAthome") {
        throw "The packaged application home page failed its smoke test."
    }

    Write-Host "Release smoke test passed on port $Port."
}
finally {
    if ($null -ne $process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force
        $process.WaitForExit()
    }
    $env:PDFEDITORATHOME_PORT = $previousPort
    $env:PDFEDITORATHOME_NO_BROWSER = $previousNoBrowser
}
