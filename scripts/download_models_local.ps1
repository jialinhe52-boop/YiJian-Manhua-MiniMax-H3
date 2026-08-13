$ErrorActionPreference = "Stop"

$modelRoot = "F:\YiJian-Manhua-H3-Models"
$chunkSize = 64MB
$maxParallel = 8
$files = @(
    @{
        Path = "diffusion_models\minimax_h3_fl2va_pruned_int8_convrot.safetensors"
        Size = 20970379616
        Url = "https://modelscope.cn/models/Comfy-Org/MiniMax-H3/resolve/master/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors"
    },
    @{
        Path = "diffusion_models\minimax_h3_ref2va_pruned_int8_convrot.safetensors"
        Size = 20970379616
        Url = "https://modelscope.cn/models/Comfy-Org/MiniMax-H3/resolve/master/diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors"
    },
    @{
        Path = "text_encoders\qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
        Size = 15687142551
        Url = "https://modelscope.cn/models/Comfy-Org/MiniMax-H3/resolve/master/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
    },
    @{
        Path = "vae\minimax_h3_video_vae_fp16.safetensors"
        Size = 5207808496
        Url = "https://modelscope.cn/models/Comfy-Org/MiniMax-H3/resolve/master/vae/minimax_h3_video_vae_fp16.safetensors"
    },
    @{
        Path = "vae\minimax_h3_audio_vae_fp32.safetensors"
        Size = 605254808
        Url = "https://modelscope.cn/models/Comfy-Org/MiniMax-H3/resolve/master/vae/minimax_h3_audio_vae_fp32.safetensors"
    },
    @{
        Path = "loras\minimax_h3_turbo_v4_step600_ema.safetensors"
        Size = 779849816
        Url = "https://hf-mirror.com/larryvrh/MiniMax-H3-Turbo-Lora/resolve/main/minimax_h3_turbo_v4_step600_ema.safetensors"
    }
)

function Join-Parts {
    param([string]$PartsDirectory, [string]$Destination, [long]$ExpectedSize)

    $assembling = "$Destination.assembling"
    $output = [System.IO.File]::Open($assembling, [System.IO.FileMode]::Create)
    try {
        Get-ChildItem -LiteralPath $PartsDirectory -Filter "*.part" |
            Sort-Object Name |
            ForEach-Object {
                $input = [System.IO.File]::OpenRead($_.FullName)
                try { $input.CopyTo($output) } finally { $input.Dispose() }
            }
    } finally {
        $output.Dispose()
    }
    if ((Get-Item -LiteralPath $assembling).Length -ne $ExpectedSize) {
        throw "assembled size mismatch for $Destination"
    }
    Move-Item -LiteralPath $assembling -Destination $Destination -Force
}

function Invoke-SegmentedDownload {
    param([string]$Url, [string]$Destination, [long]$ExpectedSize)

    $partsDirectory = "$Destination.parts"
    New-Item -ItemType Directory -Force -Path $partsDirectory | Out-Null
    $pending = New-Object System.Collections.Queue
    $chunkCount = [Math]::Ceiling($ExpectedSize / $chunkSize)
    for ($index = 0; $index -lt $chunkCount; $index++) {
        $start = [long]$index * $chunkSize
        $end = [Math]::Min($ExpectedSize - 1, $start + $chunkSize - 1)
        $part = Join-Path $partsDirectory ("{0:D5}.part" -f $index)
        $expectedPartSize = $end - $start + 1
        if ((Test-Path -LiteralPath $part) -and (Get-Item -LiteralPath $part).Length -eq $expectedPartSize) {
            continue
        }
        $pending.Enqueue(@{ Index = $index; Start = $start; End = $end; Path = $part; Size = $expectedPartSize })
    }

    $active = @()
    while ($pending.Count -gt 0 -or $active.Count -gt 0) {
        while ($pending.Count -gt 0 -and $active.Count -lt $maxParallel) {
            $chunk = $pending.Dequeue()
            if (Test-Path -LiteralPath $chunk.Path) { Remove-Item -LiteralPath $chunk.Path -Force }
            $arguments = @(
                "--location", "--fail", "--retry", "20", "--retry-all-errors",
                "--connect-timeout", "30", "--speed-time", "60", "--speed-limit", "1024",
                "--range", "$($chunk.Start)-$($chunk.End)", "--output", $chunk.Path, $Url
            )
            $process = Start-Process -FilePath "curl.exe" -ArgumentList $arguments -WindowStyle Hidden -PassThru
            $active += @{ Process = $process; Chunk = $chunk }
        }

        Start-Sleep -Seconds 2
        $remaining = @()
        foreach ($item in $active) {
            if (-not $item.Process.HasExited) {
                $remaining += $item
                continue
            }
            $chunk = $item.Chunk
            $valid = (Test-Path -LiteralPath $chunk.Path) -and
                ((Get-Item -LiteralPath $chunk.Path).Length -eq $chunk.Size)
            if (-not $valid) {
                $pending.Enqueue($chunk)
            }
        }
        $active = $remaining
        $completedBytes = (Get-ChildItem -LiteralPath $partsDirectory -Filter "*.part" |
            Measure-Object -Property Length -Sum).Sum
        Write-Output ("PROGRESS {0} {1:N2}%" -f $Destination, (100 * $completedBytes / $ExpectedSize))
    }

    Join-Parts $partsDirectory $Destination $ExpectedSize
    Remove-Item -LiteralPath $partsDirectory -Recurse -Force
}

foreach ($file in $files) {
    $target = Join-Path $modelRoot $file.Path
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    if ((Test-Path -LiteralPath $target) -and (Get-Item -LiteralPath $target).Length -eq $file.Size) {
        Write-Output "READY $($file.Path)"
        continue
    }
    Write-Output "DOWNLOAD $($file.Path)"
    Invoke-SegmentedDownload $file.Url $target $file.Size
    Write-Output "READY $($file.Path)"
}

Write-Output "ALL_MODELS_READY"
