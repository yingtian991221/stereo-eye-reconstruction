param(
    [string]$SourceRoot = '\\YZ\2023fall1\driving__frames_cleanpass\frames_cleanpass',
    [string]$TargetRoot = 'C:\Users\yingt\Datasets\PIRATE\driving_forward_speed'
)

$ErrorActionPreference = 'Stop'

# These are the folders read by generate_right in the four forward Driving scripts,
# plus ground truth and HEVC frames for quality comparisons. Historical outputs,
# other bitrates, and backwards scenes are intentionally excluded.
$workloads = @(
    @{ Relative = '15mm_focallength\scene_forwards\aaa'; Folders = @('8_left', '8_right', '10_left', '10_right', 'gray_depth', 'gray_u_past', 'gray_v_past', 'left', 'right', '5_left', '5_right') },
    @{ Relative = '15mm_focallength\scene_forwards\bbb'; Folders = @('14_left', '14_right', '8_left', '8_right', '05_depth', '025_u_past', '025_v_past', 'left', 'right', '5_left', '5_right') },
    @{ Relative = '35mm_focallength\scene_forwards\aaa'; Folders = @('14_left', '14_right', '10_left', '10_right', '05_depth', '025_u_past', '025_v_past', 'left', 'right', '5_left', '5_right') },
    @{ Relative = '35mm_focallength\scene_forwards\bbb'; Folders = @('8_left', '8_right', '05_depth', '025_u_past', '025_v_past', 'left', 'right', '5_left', '5_right') }
)

New-Item -ItemType Directory -Force -Path $TargetRoot | Out-Null
$copyLog = Join-Path $TargetRoot 'copy.log'

foreach ($workload in $workloads) {
    $sourceWorkload = Join-Path $SourceRoot $workload.Relative
    $targetWorkload = Join-Path $TargetRoot $workload.Relative
    New-Item -ItemType Directory -Force -Path $targetWorkload | Out-Null

    foreach ($folder in $workload.Folders) {
        $source = Join-Path $sourceWorkload $folder
        $target = Join-Path $targetWorkload $folder
        if (-not (Test-Path -LiteralPath $source -PathType Container)) {
            throw "Missing source directory: $source"
        }
        Write-Output "Copying $($workload.Relative)\$folder"
        & robocopy $source $target /E /MT:16 /R:2 /W:2 /NP /NFL /NDL /NJH /NJS "/LOG+:$copyLog" | Out-Null
        if ($LASTEXITCODE -ge 8) {
            throw "robocopy failed ($LASTEXITCODE): $source"
        }
    }

    # Keep each workload's original script and scalar side data together.
    & robocopy $sourceWorkload $targetWorkload '*.npy' '*.py' /R:2 /W:2 /NP /NFL /NDL /NJH /NJS "/LOG+:$copyLog" | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed ($LASTEXITCODE): $sourceWorkload sidecars"
    }
}

Write-Output "Copied selected Driving inputs to $TargetRoot"
Write-Output "Robocopy log: $copyLog"
