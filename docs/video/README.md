# How the demo video was made

Every terminal line in the video comes from a real run on AWS (us-east-1, Oct 25 2026): the
`--before` run, the `--after` run, and the SQS wake-up worker log. The Scheduler shot is a
real console screenshot taken while wake #1 was pending.

- `narration.json`: script, voiced with [Piper](https://github.com/rhasspy/piper) (`en_US-lessac-high`)
- `video.html`: scenes, rendered frame by frame (24 fps) with Playwright
- `render.py`: builds the narration track, captures frames, muxes with ffmpeg

To rebuild: put `video.html`, `scheduler_crop.png` and the per-scene `s1..s9.wav` in `build/`, then run `python render.py full`.
