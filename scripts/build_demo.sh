#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
render_dir="$(mktemp -d)"

for slide in "$repo_dir"/docs/assets/demo-slide-*.svg; do
  qlmanage -t -s 1280 -o "$render_dir" "$slide" >/dev/null 2>&1
done

ffmpeg -y \
  -loop 1 -t 4 -i "$render_dir/demo-slide-1.svg.png" \
  -loop 1 -t 4 -i "$render_dir/demo-slide-2.svg.png" \
  -loop 1 -t 4 -i "$render_dir/demo-slide-3.svg.png" \
  -loop 1 -t 4 -i "$render_dir/demo-slide-4.svg.png" \
  -loop 1 -t 4 -i "$render_dir/demo-slide-5.svg.png" \
  -filter_complex "[0:v]crop=1280:720:0:280,fps=30,format=yuv420p[v0];[1:v]crop=1280:720:0:280,fps=30,format=yuv420p[v1];[2:v]crop=1280:720:0:280,fps=30,format=yuv420p[v2];[3:v]crop=1280:720:0:280,fps=30,format=yuv420p[v3];[4:v]crop=1280:720:0:280,fps=30,format=yuv420p[v4];[v0][v1][v2][v3][v4]concat=n=5:v=1:a=0[out]" \
  -map "[out]" -c:v libx264 -pix_fmt yuv420p -movflags +faststart -an "$repo_dir/docs/demo.mp4"

echo "Created $repo_dir/docs/demo.mp4"
