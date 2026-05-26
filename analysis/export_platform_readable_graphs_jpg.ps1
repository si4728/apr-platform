param(
    [string]$InputDir = "experiment_results\paper_figures",
    [string]$OutputDir = "experiment_results\paper_figures"
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

function Get-Double($value, [double]$default = 0.0) {
    if ($null -eq $value -or "$value" -eq "") { return $default }
    $parsed = 0.0
    if ([double]::TryParse("$value", [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$parsed)) {
        return $parsed
    }
    return $default
}

function Save-Jpeg($bitmap, $path, [long]$quality = 95) {
    $codec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() |
        Where-Object { $_.MimeType -eq "image/jpeg" } |
        Select-Object -First 1
    $encoder = [System.Drawing.Imaging.Encoder]::Quality
    $params = New-Object System.Drawing.Imaging.EncoderParameters 1
    $params.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter $encoder, $quality
    $bitmap.Save($path, $codec, $params)
    $params.Dispose()
}

function Get-X($index, $count, $left, $width) {
    if ($count -le 1) { return $left + ($width / 2) }
    return $left + ($index * $width / ($count - 1))
}

function Get-Y($value, $min, $max, $top, $height) {
    if ($max -le $min) { return $top + ($height / 2) }
    $n = ([double]$value - [double]$min) / ([double]$max - [double]$min)
    return $top + $height - ($n * $height)
}

function Draw-Axes($g, $left, $top, $width, $height, $title, $yLabel, $xLabels, $font, $smallFont, $brush, $pen) {
    $g.DrawRectangle($pen, $left, $top, $width, $height)
    $g.DrawString($title, $font, $brush, $left, $top - 24)
    $g.DrawString($yLabel, $smallFont, $brush, 24, $top + 8)
    $count = $xLabels.Count
    for ($i = 0; $i -lt $count; $i++) {
        $x = Get-X $i $count $left $width
        $g.DrawLine($pen, $x, ($top + $height), $x, ($top + $height + 4))
        $g.DrawString($xLabels[$i], $smallFont, $brush, ($x - 12), ($top + $height + 8))
    }
}

function Draw-Line($g, $values, $min, $max, $left, $top, $width, $height, $pen) {
    if ($values.Count -lt 2) { return }
    for ($i = 1; $i -lt $values.Count; $i++) {
        $x1 = Get-X ($i - 1) $values.Count $left $width
        $y1 = Get-Y (Get-Double $values[$i - 1]) $min $max $top $height
        $x2 = Get-X $i $values.Count $left $width
        $y2 = Get-Y (Get-Double $values[$i]) $min $max $top $height
        $g.DrawLine($pen, $x1, $y1, $x2, $y2)
    }
}

function Draw-Markers($g, $values, $baseline, $left, $top, $width, $height, $brush, $label, $font) {
    for ($i = 0; $i -lt $values.Count; $i++) {
        if ((Get-Double $values[$i]) -eq 1) {
            $x = Get-X $i $values.Count $left $width
            $g.FillEllipse($brush, ($x - 5), ($baseline - 5), 10, 10)
            $g.DrawLine((New-Object System.Drawing.Pen $brush.Color, 1), $x, $top, $x, ($top + $height))
            $g.DrawString($label, $font, $brush, ($x + 7), ($baseline - 9))
        }
    }
}

function Draw-Fig6Timeline($rows, $path) {
    $width = 1180
    $height = 760
    $left = 110
    $chartW = 980
    $panelH = 130
    $gap = 54
    $top1 = 115
    $top2 = $top1 + $panelH + $gap
    $top3 = $top2 + $panelH + $gap
    $top4 = $top3 + $panelH + $gap

    $bmp = New-Object System.Drawing.Bitmap $width, $height
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    $g.Clear([System.Drawing.Color]::White)

    $titleFont = New-Object System.Drawing.Font "Arial", 22, ([System.Drawing.FontStyle]::Bold)
    $panelFont = New-Object System.Drawing.Font "Arial", 12, ([System.Drawing.FontStyle]::Bold)
    $font = New-Object System.Drawing.Font "Arial", 9
    $smallFont = New-Object System.Drawing.Font "Arial", 8
    $textBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(23, 32, 51))
    $mutedBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(82, 94, 110))
    $gridPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(210, 218, 228)), 1
    $ratePen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(36, 104, 178)), 3
    $queuePen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(238, 129, 30)), 3
    $latPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(186, 52, 69)), 3
    $policyBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(62, 132, 86))
    $rollbackBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(186, 52, 69))
    $stableBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(36, 104, 178))

    $labels = @($rows | ForEach-Object timestamp)
    $publish = @($rows | ForEach-Object { Get-Double $_.publish_count })
    $queue = @($rows | ForEach-Object { Get-Double $_.queue_depth })
    $p95 = @($rows | ForEach-Object { (Get-Double $_.p95_latency) * 1000.0 })
    $policy = @($rows | ForEach-Object { Get-Double $_.policy_update_flag })
    $rollback = @($rows | ForEach-Object { Get-Double $_.rollback_flag })
    $stable = @($rows | ForEach-Object { Get-Double $_.stabilization_flag })

    $maxPublish = [math]::Max(1, ($publish | Measure-Object -Maximum).Maximum)
    $maxQueue = [math]::Max(1, ($queue | Measure-Object -Maximum).Maximum)
    $maxP95 = [math]::Max(1, ($p95 | Measure-Object -Maximum).Maximum)

    $g.DrawString("platform-Fig. 6. Runtime Adaptive Communication Timeline", $titleFont, $textBrush, 28, 26)
    $g.DrawString("Runtime telemetry, backlog, p95 latency, and adaptive-control events are separated into readable panels.", $font, $mutedBrush, 30, 62)

    Draw-Axes $g $left $top1 $chartW $panelH "Telemetry Rate" "msg/s" $labels $panelFont $smallFont $textBrush $gridPen
    Draw-Line $g $publish 0 $maxPublish $left $top1 $chartW $panelH $ratePen

    Draw-Axes $g $left $top2 $chartW $panelH "Queue Accumulation" "depth" $labels $panelFont $smallFont $textBrush $gridPen
    Draw-Line $g $queue 0 $maxQueue $left $top2 $chartW $panelH $queuePen

    Draw-Axes $g $left $top3 $chartW $panelH "Tail Latency Evolution" "p95 ms" $labels $panelFont $smallFont $textBrush $gridPen
    Draw-Line $g $p95 0 $maxP95 $left $top3 $chartW $panelH $latPen

    Draw-Axes $g $left $top4 $chartW 70 "APR Control Events" "event" $labels $panelFont $smallFont $textBrush $gridPen
    Draw-Markers $g $policy ($top4 + 18) $left $top4 $chartW 70 $policyBrush "Policy" $font
    Draw-Markers $g $rollback ($top4 + 38) $left $top4 $chartW 70 $rollbackBrush "Rollback" $font
    Draw-Markers $g $stable ($top4 + 58) $left $top4 $chartW 70 $stableBrush "Stable" $font

    $g.DrawString("Blue: telemetry/p95 context, orange: backlog, green/red/blue markers: policy/rollback/stabilization.", $smallFont, $mutedBrush, 30, 724)

    Save-Jpeg $bmp $path 95

    $g.Dispose(); $bmp.Dispose()
    $titleFont.Dispose(); $panelFont.Dispose(); $font.Dispose(); $smallFont.Dispose()
    $textBrush.Dispose(); $mutedBrush.Dispose(); $gridPen.Dispose()
    $ratePen.Dispose(); $queuePen.Dispose(); $latPen.Dispose()
    $policyBrush.Dispose(); $rollbackBrush.Dispose(); $stableBrush.Dispose()
}

function Draw-Fig7Stacked($rows, $path) {
    $width = 1180
    $height = 720
    $left = 115
    $top = 120
    $chartW = 920
    $chartH = 430

    $bmp = New-Object System.Drawing.Bitmap $width, $height
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    $g.Clear([System.Drawing.Color]::White)

    $titleFont = New-Object System.Drawing.Font "Arial", 22, ([System.Drawing.FontStyle]::Bold)
    $font = New-Object System.Drawing.Font "Arial", 9
    $smallFont = New-Object System.Drawing.Font "Arial", 8
    $textBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(23, 32, 51))
    $mutedBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(82, 94, 110))
    $gridPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(210, 218, 228)), 1
    $p95Pen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(180, 46, 58)), 3
    $p99Pen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(85, 39, 145)), 3
    $queueColors = @(
        [System.Drawing.Color]::FromArgb(194, 222, 235),
        [System.Drawing.Color]::FromArgb(124, 190, 206),
        [System.Drawing.Color]::FromArgb(247, 190, 105),
        [System.Drawing.Color]::FromArgb(235, 135, 88),
        [System.Drawing.Color]::FromArgb(178, 82, 92)
    )
    $stageNames = @("TxQ", "BrokerQ", "RelayQ", "SubscriberQ", "PlaybackQ")

    $labels = @($rows | ForEach-Object timestamp)
    $series = @(
        @($rows | ForEach-Object { Get-Double $_.tx_queue_depth }),
        @($rows | ForEach-Object { Get-Double $_.broker_queue_depth }),
        @($rows | ForEach-Object { Get-Double $_.relay_queue_depth }),
        @($rows | ForEach-Object { Get-Double $_.subscriber_queue_depth }),
        @($rows | ForEach-Object { Get-Double $_.playback_queue_depth })
    )
    $p95 = @($rows | ForEach-Object { (Get-Double $_.p95_latency) * 1000.0 })
    $p99 = @($rows | ForEach-Object { (Get-Double $_.p99_latency) * 1000.0 })

    $stackTotals = @()
    for ($i = 0; $i -lt $labels.Count; $i++) {
        $sum = 0.0
        for ($s = 0; $s -lt $series.Count; $s++) { $sum += $series[$s][$i] }
        $stackTotals += $sum
    }
    $maxStack = [math]::Max(1, ($stackTotals | Measure-Object -Maximum).Maximum)
    $maxLatency = [math]::Max(1, (($p95 + $p99) | Measure-Object -Maximum).Maximum)

    $g.DrawString("platform-Fig. 7. Distributed Queue Propagation and Tail Latency Amplification", $titleFont, $textBrush, 28, 26)
    $g.DrawString("Stacked queue stages expose backlog propagation; p95/p99 lines show tail latency amplification.", $font, $mutedBrush, 30, 62)
    $g.DrawRectangle($gridPen, $left, $top, $chartW, $chartH)
    $g.DrawString("Queue depth, stacked by runtime stage", $font, $textBrush, 28, $top + 8)
    $g.DrawString("Latency ms", $font, $textBrush, $left + $chartW + 14, $top + 8)

    for ($tick = 0; $tick -le 4; $tick++) {
        $y = $top + $chartH - ($tick * $chartH / 4)
        $g.DrawLine($gridPen, $left, $y, ($left + $chartW), $y)
        $g.DrawString(([math]::Round($maxStack * $tick / 4, 1)).ToString(), $smallFont, $mutedBrush, 72, ($y - 8))
    }

    $baseline = @()
    for ($i = 0; $i -lt $labels.Count; $i++) { $baseline += 0.0 }

    for ($s = 0; $s -lt $series.Count; $s++) {
        $points = New-Object System.Collections.Generic.List[System.Drawing.PointF]
        for ($i = 0; $i -lt $labels.Count; $i++) {
            $x = Get-X $i $labels.Count $left $chartW
            $y = Get-Y ($baseline[$i] + $series[$s][$i]) 0 $maxStack $top $chartH
            $points.Add((New-Object System.Drawing.PointF $x, $y))
        }
        for ($i = $labels.Count - 1; $i -ge 0; $i--) {
            $x = Get-X $i $labels.Count $left $chartW
            $y = Get-Y $baseline[$i] 0 $maxStack $top $chartH
            $points.Add((New-Object System.Drawing.PointF $x, $y))
        }
        $brush = New-Object System.Drawing.SolidBrush $queueColors[$s]
        $g.FillPolygon($brush, $points.ToArray())
        $brush.Dispose()
        for ($i = 0; $i -lt $labels.Count; $i++) { $baseline[$i] += $series[$s][$i] }
    }

    Draw-Line $g $p95 0 $maxLatency $left $top $chartW $chartH $p95Pen
    Draw-Line $g $p99 0 $maxLatency $left $top $chartW $chartH $p99Pen

    for ($i = 0; $i -lt $labels.Count; $i++) {
        $x = Get-X $i $labels.Count $left $chartW
        $g.DrawLine($gridPen, $x, ($top + $chartH), $x, ($top + $chartH + 4))
        $g.DrawString($labels[$i], $smallFont, $mutedBrush, ($x - 12), ($top + $chartH + 12))
    }

    $legendX = $left
    $legendY = $top + $chartH + 56
    for ($s = 0; $s -lt $stageNames.Count; $s++) {
        $brush = New-Object System.Drawing.SolidBrush $queueColors[$s]
        $x = $legendX + $s * 145
        $g.FillRectangle($brush, $x, $legendY, 18, 12)
        $g.DrawString($stageNames[$s], $smallFont, $textBrush, ($x + 24), ($legendY - 2))
        $brush.Dispose()
    }
    $g.DrawLine($p95Pen, $legendX, ($legendY + 34), ($legendX + 38), ($legendY + 34))
    $g.DrawString("p95 latency", $smallFont, $textBrush, ($legendX + 46), ($legendY + 26))
    $g.DrawLine($p99Pen, ($legendX + 150), ($legendY + 34), ($legendX + 188), ($legendY + 34))
    $g.DrawString("p99 latency", $smallFont, $textBrush, ($legendX + 196), ($legendY + 26))
    $g.DrawString("Tail Latency Amplification Zone", (New-Object System.Drawing.Font "Arial", 12, ([System.Drawing.FontStyle]::Bold)), (New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(138, 31, 17))), ($left + $chartW - 260), ($top + 28))

    Save-Jpeg $bmp $path 95

    $g.Dispose(); $bmp.Dispose()
    $titleFont.Dispose(); $font.Dispose(); $smallFont.Dispose()
    $textBrush.Dispose(); $mutedBrush.Dispose(); $gridPen.Dispose()
    $p95Pen.Dispose(); $p99Pen.Dispose()
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$fig6Csv = Join-Path $InputDir "platform_fig6_runtime_adaptive_communication.csv"
$fig7Csv = Join-Path $InputDir "platform_fig7_queue_propagation.csv"
if (-not (Test-Path $fig6Csv)) { throw "Missing $fig6Csv. Run generate_platform_fig6_fig7.py first." }
if (-not (Test-Path $fig7Csv)) { throw "Missing $fig7Csv. Run generate_platform_fig6_fig7.py first." }

$fig6Rows = @(Import-Csv $fig6Csv)
$fig7Rows = @(Import-Csv $fig7Csv)

$fig6Out = Join-Path $OutputDir "platform_fig6_runtime_adaptive_timeline.jpg"
$fig7Out = Join-Path $OutputDir "platform_fig7_queue_propagation_stacked_latency.jpg"

Draw-Fig6Timeline $fig6Rows $fig6Out
Draw-Fig7Stacked $fig7Rows $fig7Out

Write-Host "Generated:"
Write-Host "  $fig6Out"
Write-Host "  $fig7Out"
