param(
  [Parameter(Mandatory = $true)]
  [string]$RunId,

  [ValidateSet("auto", "all", "render")]
  [string]$Stage = "auto",

  [switch]$Execute
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$argsList = @(".\scripts\retry_run.py", $RunId, "--stage", $Stage)
if ($Execute) { $argsList += "--execute" }
python @argsList
