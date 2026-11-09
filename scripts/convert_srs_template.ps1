$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$templatePath = 'C:\Users\Aadyant Neog\Downloads\srs_template-ieee.doc'
$inspectionDir = Join-Path $projectRoot 'tmp\ieee-srs'
New-Item -ItemType Directory -Force -Path $inspectionDir | Out-Null
$sourceHash = (Get-FileHash -LiteralPath $templatePath -Algorithm SHA256).Hash
$originalSrs = Join-Path $projectRoot 'output\pdf\YouTube_Video_Intelligence_SRS.pdf'
$originalSrsHash = (Get-FileHash -LiteralPath $originalSrs -Algorithm SHA256).Hash
$word = $null
$document = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    $word.Options.UpdateLinksAtOpen = $false
    $document = $word.Documents.Open($templatePath, $false, $true, $false)
    $text = $document.Content.Text
    [System.IO.File]::WriteAllText((Join-Path $inspectionDir 'template.txt'), $text)
    $document.SaveAs2((Join-Path $inspectionDir 'template-reference.docx'), 16)
    $document.ExportAsFixedFormat((Join-Path $inspectionDir 'template-reference.pdf'), 17)
    [System.IO.File]::WriteAllText((Join-Path $inspectionDir 'preservation.json'), (@{
        template_path = $templatePath
        template_sha256 = $sourceHash
        original_srs_path = $originalSrs
        original_srs_sha256 = $originalSrsHash
    } | ConvertTo-Json))
    Write-Output 'Converted the legacy template for inspection; original files retained.'
} finally {
    if ($null -ne $document) { $document.Close(0); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($document) }
    if ($null -ne $word) { $word.Quit(); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) }
}
if ((Get-FileHash -LiteralPath $templatePath -Algorithm SHA256).Hash -ne $sourceHash) { throw 'Template preservation check failed' }
if ((Get-FileHash -LiteralPath $originalSrs -Algorithm SHA256).Hash -ne $originalSrsHash) { throw 'Original SRS preservation check failed' }
