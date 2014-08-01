#!/bin/bash

set -e
set -u

source "$(dirname "$0")"/variables.inc

CATEGORY="$1"

cd "$FILES_ROOT" || exit 1
test -d "$CATEGORY" || exit 1
test -f "$MUSIC_BACKGROUND" || exit 1

for MUSIC_FILE in "$CATEGORY"/{*.wav,*.ogg,*.mp3,*.flac}; do
    [[ -f "$MUSIC_FILE" ]] || continue
    TARGET_FILE="$MUSIC_FILE".mp4

    avconv -loop 1 -r 10 -i "$MUSIC_BACKGROUND" -i "$MUSIC_FILE" -strict experimental -acodec aac -b:a 256k -vcodec libx264 -r 10 -me_method zero -crf 4 -preset ultrafast -shortest -y "$TARGET_FILE"
done
