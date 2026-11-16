#!/usr/bin/env bash
# Build the voice track from the two recordings and mix it with the synthesized music and effects.
#   bash video/tools/mix_audio.sh          (run after tools/render.mjs and tools/make_audio.py)
# Output: out/video_1080p60_final.mp4 and out/preview_720p_final.mp4
set -euo pipefail
cd "$(dirname "$0")/../audio"
CLEAN="highpass=f=85,afftdn=nf=-28,acompressor=threshold=-22dB:ratio=3:attack=8:release=120:makeup=2,loudnorm=I=-15:TP=-1.5:LRA=9"

# 1) first recording: lead silence cut, intro sentence sped up 1.25x (pitch kept), the "aboard Terra and Aqua,
#    Suomi NPP and NOAA-20" clause cut (it repeats the DATASETS panel)
ffmpeg -v error -y -i voice_raw.mp4 -filter_complex \
 "[0:a]atrim=0.45:10.2,asetpts=PTS-STARTPTS,atempo=1.25[a1];[0:a]atrim=10.2:21.22,asetpts=PTS-STARTPTS,afade=t=out:st=10.92:d=0.1[a2];[a1][a2]concat=n=2:v=0:a=1,$CLEAN" \
 -ar 48000 -ac 2 voice_clean.wav

# 2) second recording: five lines, each placed on its slide at normal speed
ffmpeg -v error -y -i voice2_raw.mp4 -af "$CLEAN" -ar 48000 -ac 2 voice2_clean.wav
line() { echo "[1:a]atrim=$1:$2,asetpts=PTS-STARTPTS,afade=t=in:d=0.03,afade=t=out:st=$(python -c "print(round($2-$1-0.1,3))"):d=0.1,adelay=$3|$3[$4];"; }
ffmpeg -v error -y -i voice_clean.wav -i voice2_clean.wav -filter_complex \
 "$(line 1.90 4.50 18950 s1)$(line 5.00 6.60 21200 s2)$(line 6.70 8.60 23250 s3)$(line 8.88 11.60 25100 s4)$(line 12.58 13.75 28600 s5)[0:a]apad=whole_dur=30[b];[b][s1][s2][s3][s4][s5]amix=inputs=6:normalize=0:duration=first" \
 -t 30 -ar 48000 -ac 2 voice_full.wav

# 3) final mix: music ducks under the voice
cd ../out
ffmpeg -v error -y -i video_1080p60.mp4 -i ../audio/voice_full.wav -i ../audio/music.wav -i ../audio/sfx.wav -filter_complex \
 "[1:a]asplit=2[v1][vkey];[2:a]volume=0.5[m];[m][vkey]sidechaincompress=threshold=0.03:ratio=6:attack=15:release=400[md];[3:a]volume=0.7[s];[v1][md][s]amix=inputs=3:normalize=0:duration=first,alimiter=limit=0.95,loudnorm=I=-14:TP=-1.0:LRA=11,aresample=48000[a]" \
 -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -t 30 -movflags +faststart video_1080p60_final.mp4
ffmpeg -v error -y -i video_1080p60_final.mp4 -vf scale=1280:-2 -r 30 -c:v libx264 -preset slow -crf 25 -pix_fmt yuv420p \
 -c:a aac -b:a 128k -movflags +faststart preview_720p_final.mp4
echo done
