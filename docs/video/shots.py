import json
from playwright.sync_api import sync_playwright
B="/home/claude/video/build"; O="/home/claude/video/img"
import os; os.makedirs(O,exist_ok=True)
sc=json.load(open(f"{B}/scenes.json")); st={s["id"]:s["start"] for s in sc}
with sync_playwright() as p:
    b=p.chromium.launch()
    pg=b.new_page(viewport={"width":1200,"height":675}); pg.goto(f"file://{B}/cover.html"); pg.wait_for_timeout(300); pg.screenshot(path=f"{O}/cover.png")
    pg=b.new_page(viewport={"width":1600,"height":760}); pg.goto(f"file://{B}/arch.html"); pg.wait_for_timeout(300); pg.screenshot(path=f"{O}/architecture.png")
    pg=b.new_page(viewport={"width":1920,"height":1080})
    pg.add_init_script(f"window.SCENES={json.dumps(sc)};"); pg.goto(f"file://{B}/video.html"); pg.wait_for_timeout(400)
    for name,sid,rel in [("before_empty_promise","s3",11.5),("after_scheduler","s5",8.5),("wake1_reschedule","s6",9.5),("wake2_email","s7",11.5),("eval","s8",23.0)]:
        pg.evaluate(f"render({st[sid]+rel})"); pg.evaluate("document.getElementById('cap').style.display='none';document.getElementById('prog').style.display='none'")
        pg.screenshot(path=f"{O}/{name}.png")
    b.close()
