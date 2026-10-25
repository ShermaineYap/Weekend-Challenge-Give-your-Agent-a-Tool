import json, subprocess, sys, wave, os
from playwright.sync_api import sync_playwright
import pathlib; B = str(pathlib.Path(__file__).parent / "build")
narr = json.load(open(str(pathlib.Path(__file__).parent / "narration.json")))
LEAD, TAIL = 0.5, 1.0
scenes, t = [], 0.0
for sid, text in narr:
    a = float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",f"{B}/{sid}.wav"],capture_output=True,text=True).stdout)
    dur = LEAD + a + TAIL + (0.8 if sid == "s9" else 0)
    scenes.append({"id": sid, "start": round(t,3), "dur": round(dur,3), "lead": LEAD, "audio": a, "text": text})
    t += dur
TOTAL = t
json.dump(scenes, open(f"{B}/scenes.json","w"))

def audio():
    frames = []
    params = None
    for sc in scenes:
        w = wave.open(f"{B}/{sc['id']}.wav"); params = w.getparams()
        sr, sw = w.getframerate(), w.getsampwidth()
        data = w.readframes(w.getnframes()); w.close()
        pre = b"\0" * int(LEAD * sr) * sw
        post_len = int(round(sc["start"] + sc["dur"], 3) * sr) - int(round(sc["start"], 3) * sr) - len(data)//sw - int(LEAD*sr)
        frames.append(pre + data + b"\0" * max(0, post_len) * sw)
    out = wave.open(f"{B}/narration.wav","wb"); out.setparams(params); out.writeframes(b"".join(frames)); out.close()

def frames(times, outdir, fmt="frame_%05d.jpg"):
    os.makedirs(outdir, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width":1920,"height":1080})
        pg.add_init_script(f"window.SCENES = {json.dumps(scenes)};")
        pg.goto(f"file://{B}/video.html"); pg.wait_for_timeout(500)
        for i, tt in enumerate(times):
            pg.evaluate(f"render({tt})")
            pg.screenshot(path=os.path.join(outdir, fmt % i) if "%" in fmt else os.path.join(outdir, f"{tt:06.2f}.jpg"), type="jpeg", quality=90)
        b.close()

if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "preview":
        ts = [float(x) for x in sys.argv[2:]] if len(sys.argv) > 2 else [sc["start"] + sc["dur"]*0.8 for sc in scenes]
        frames(ts, f"{B}/preview", fmt="t")
        print("total", round(TOTAL,2), [ (s["id"], s["start"]) for s in scenes])
    else:
        FPS = 24
        audio()
        n = int(TOTAL * FPS)
        frames([i / FPS for i in range(n)], f"{B}/frames")
        subprocess.run(["ffmpeg","-y","-loglevel","error","-framerate",str(FPS),"-i",f"{B}/frames/frame_%05d.jpg","-i",f"{B}/narration.wav",
                        "-c:v","libx264","-pix_fmt","yuv420p","-crf","18","-preset","medium","-c:a","aac","-b:a","160k","-shortest","-movflags","+faststart",
                        str(pathlib.Path(__file__).parent.parent / "patience_demo.mp4")], check=True)
        print("done", TOTAL)
