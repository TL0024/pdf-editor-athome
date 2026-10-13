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
$testProcessName = [System.IO.Path]::GetFileNameWithoutExtension($resolvedExecutable)
$existingProcessIds = @(Get-Process -Name $testProcessName -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)

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

    $boundary = "PDFEditorSmokeBoundary"
    $importBody = "--$boundary`r`nContent-Disposition: form-data; name=`"file`"; filename=`"smoke.txt`"`r`nContent-Type: text/plain`r`n`r`nEditable packaged export`r`n--$boundary--`r`n"
    $imported = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/import" -Method Post `
        -ContentType "multipart/form-data; boundary=$boundary" -Body ([System.Text.Encoding]::UTF8.GetBytes($importBody))
    $sourcePage = $imported.pages[0]
    $exportBody = @{
        name = "Packaged smoke test"
        format = "docx"
        pages = @(@{
            width = $sourcePage.width
            height = $sourcePage.height
            pointsPerPixel = $sourcePage.pointsPerPixel
            documentId = $imported.documentId
            serverIndex = $sourcePage.serverIndex
            annotations = @($sourcePage.annotations)
        })
    } | ConvertTo-Json -Depth 20 -Compress
    $wordResponse = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/export" -Method Post `
        -ContentType "application/json" -Body $exportBody -UseBasicParsing -TimeoutSec 15
    Add-Type -AssemblyName System.IO.Compression
    $archive = [System.IO.Compression.ZipArchive]::new($wordResponse.RawContentStream)
    try {
        $entry = $archive.GetEntry("word/document.xml")
        $reader = [System.IO.StreamReader]::new($entry.Open())
        try { $wordXml = $reader.ReadToEnd() } finally { $reader.Dispose() }
        if ($wordXml -notmatch "Editable packaged export" -or $wordXml -match "<w:drawing") {
            throw "The packaged Word export did not contain editable text."
        }
    }
    finally { $archive.Dispose() }

    Write-Host "Release smoke test passed on port $Port, including editable Word export."
}
finally {
    if ($null -ne $process -and -not $process.HasExited) {
        # A PyInstaller one-file executable starts a child process for the app.
        # Track only new instances of this executable created by this smoke run.
        $testProcesses = @(Get-Process -Name $testProcessName -ErrorAction SilentlyContinue | Where-Object {
            $_.Id -notin $existingProcessIds -and $_.Path -eq $resolvedExecutable -and $_.StartTime -ge $process.StartTime
        })
        $testProcesses | Stop-Process -Force -ErrorAction SilentlyContinue
        if (-not $process.WaitForExit(5000)) {
            Stop-Process -Id $process.Id -Force
        }
    }
    $env:PDFEDITORATHOME_PORT = $previousPort
    $env:PDFEDITORATHOME_NO_BROWSER = $previousNoBrowser
}
