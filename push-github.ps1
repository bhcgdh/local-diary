param(
  [string]$Message = "Update local diary $(Get-Date -Format 'yyyy-MM-dd HH:mm')",
  [string]$RepoName = "local-diary",
  [ValidateSet("private", "public")]
  [string]$Visibility
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Run-Git {
  & git @args
  if ($LASTEXITCODE -ne 0) {
    throw "Git command failed: git $($args -join ' ')"
  }
}

function Run-Command {
  param(
    [string]$Exe,
    [string[]]$CommandArgs,
    [string]$FailureMessage
  )

  & $Exe @CommandArgs
  if ($LASTEXITCODE -ne 0) {
    throw $FailureMessage
  }
}

if (-not (Test-Path ".git")) {
  Write-Host "Initializing git repository..."
  Run-Git init -b main
}

Write-Host "Checking GitHub CLI authentication..."
& gh auth status
if ($LASTEXITCODE -ne 0) {
  throw "GitHub CLI is not authenticated. Run: gh auth login"
}

Write-Host "Checking changes..."
Run-Git diff --check

Write-Host "Running tests..."
Run-Command -Exe "python" -CommandArgs @("-m", "unittest", "-v") -FailureMessage "Unit tests failed."

Write-Host "Staging changes (excluding data folders)..."
Run-Git add --all -- .

$stagedDataFiles = & git diff --cached --name-only -- data datas
if ($LASTEXITCODE -ne 0) {
  throw "Unable to inspect staged data files."
}
if ($stagedDataFiles) {
  & git restore --staged -- data datas
  throw "Refusing to commit data files: $($stagedDataFiles -join ', ')"
}

& git diff --cached --quiet
if ($LASTEXITCODE -eq 1) {
  Write-Host "Creating commit: $Message"
  Run-Git commit -m $Message
} elseif ($LASTEXITCODE -ne 0) {
  throw "Unable to inspect staged changes."
} else {
  Write-Host "No new changes to commit."
}

$remotes = & git remote
if ($LASTEXITCODE -ne 0) {
  throw "Unable to inspect git remotes."
}
$hasOrigin = $remotes -contains "origin"

if (-not $hasOrigin) {
  if (-not $Visibility) {
    throw "GitHub repository does not exist yet. Re-run with -Visibility private or -Visibility public."
  }

  Write-Host "Creating GitHub repository '$RepoName' as $Visibility and pushing..."
  & gh repo create $RepoName "--$Visibility" --source . --remote origin --push
  if ($LASTEXITCODE -ne 0) {
    throw "GitHub repository creation or push failed."
  }
} else {
  Write-Host "Pushing to existing origin..."
  Run-Git push origin main
}

Write-Host "Push completed."
Run-Git status -sb
Run-Git log -1 --oneline --decorate
