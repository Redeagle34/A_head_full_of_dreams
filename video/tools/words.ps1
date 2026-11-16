# Word timings of a voice recording with the offline Windows speech recognizer (en-US dictation).
# Usage: powershell -File words.ps1 <16 kHz mono wav> <out.json>
param([string]$wav, [string]$out)
Add-Type -AssemblyName System.Speech
$culture = New-Object System.Globalization.CultureInfo('en-US')
$eng = New-Object System.Speech.Recognition.SpeechRecognitionEngine($culture)
$eng.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar))
$eng.SetInputToWaveFile($wav)
$eng.EndSilenceTimeout = [TimeSpan]::FromMilliseconds(250)
$eng.InitialSilenceTimeout = [TimeSpan]::FromSeconds(5)
$words = New-Object System.Collections.ArrayList
while ($true) {
  $r = $null
  try { $r = $eng.Recognize() } catch { break }
  if ($r -eq $null) { if ($eng.AudioPosition.TotalSeconds -ge 0 -and $eng.AudioState -eq 'Stopped') { break } else { continue } }
  foreach ($w in $r.Words) {
    $a = $r.GetAudioForWordRange($w, $w)
    [void]$words.Add([pscustomobject]@{ text = $w.Text; start = [math]::Round($a.AudioPosition.TotalSeconds, 3); dur = [math]::Round($a.Duration.TotalSeconds, 3); conf = [math]::Round($w.Confidence, 2) })
  }
  if ($eng.AudioPosition.TotalSeconds -ge 26.4) { break }
}
$words | ConvertTo-Json | Set-Content -Encoding utf8 $out
$words | ForEach-Object { "{0,6:N2} {1,5:N2}  {2}" -f $_.start, $_.dur, $_.text }
