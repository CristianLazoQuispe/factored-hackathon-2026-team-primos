"""Record and screenshot the real web app for scene 6.  Run with the stack up (make up):
/Library/Frameworks/Python.framework/Versions/3.10/bin/python3.10 docs/demo/video/scripts/capture.py [landing|corona|khipu|pngs|all]
"""
import shutil, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "public" / "screens"
WEB = "http://localhost:3000"
MIC = ROOT / "public" / "vo" / "mic-es.wav"
CASOS = ROOT.parents[2] / "web" / "public" / "casos"
VP = {"width": 1920, "height": 1080}
what = sys.argv[1] if len(sys.argv) > 1 else "all"


def sign_in(page, user):
    page.goto(WEB + "/chat", wait_until="networkidle")
    page.get_by_label("ID de cliente").fill(user)
    page.get_by_label("Contraseña").fill(user)
    page.get_by_role("button", name="Entrar").click()
    page.get_by_placeholder("Pregunta por tu saldo, un cargo o una queja…").wait_for(timeout=15000)
    time.sleep(1.0)


def save_video(page, name):
    v = page.video
    page.close()
    src = Path(v.path())
    dst = OUT / f"{name}.webm"
    shutil.move(src, dst)
    print("video", dst)


with sync_playwright() as p:
    args = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", f"--use-file-for-fake-audio-capture={MIC}%noloop", "--autoplay-policy=no-user-gesture-required"]
    browser = p.chromium.launch(args=args)

    if what in ("landing", "all"):
        ctx = browser.new_context(viewport=VP, record_video_dir=str(OUT / "tmp"), record_video_size=VP)
        page = ctx.new_page()
        page.goto(WEB + "/", wait_until="networkidle")
        time.sleep(2.0)
        for _ in range(40):
            page.mouse.wheel(0, 18)
            time.sleep(0.1)
        time.sleep(1.5)
        save_video(page, "landing")
        ctx.close()

    if what in ("corona", "all"):
        ctx = browser.new_context(viewport=VP, record_video_dir=str(OUT / "tmp"), record_video_size=VP, permissions=["microphone"])
        page = ctx.new_page()
        sign_in(page, "demo-mx-duplicate@demo.bank")
        page.get_by_role("button", name="Activar la voz de Quipu").click()
        time.sleep(1.5)
        page.get_by_role("button", name="Hablar con Quipu").click()
        time.sleep(4.5)
        page.get_by_role("button", name="Dejar de grabar").click()
        time.sleep(16.0)
        page.screenshot(path=str(OUT / "corona-end.png"))
        save_video(page, "corona")
        ctx.close()

    if what in ("khipu", "all"):
        ctx = browser.new_context(viewport=VP, record_video_dir=str(OUT / "tmp"), record_video_size=VP)
        page = ctx.new_page()
        sign_in(page, "DEMO-MX-KHIPU")
        box = page.get_by_placeholder("Pregunta por tu saldo, un cargo o una queja…")
        box.click()
        page.keyboard.type("khipea 300 a mi tarjeta", delay=55)
        time.sleep(0.6)
        page.get_by_role("button", name="Enviar").click()
        try:
            page.get_by_test_id("khipu-card").wait_for(timeout=14000)
        except Exception:
            box.click()
            page.keyboard.type("desde mi cuenta de ahorro", delay=55)
            page.get_by_role("button", name="Enviar").click()
            page.get_by_test_id("khipu-card").wait_for(timeout=40000)
        time.sleep(3.0)
        page.screenshot(path=str(OUT / "khipu.png"))
        save_video(page, "khipu")
        ctx.close()

    if what in ("pngs", "all"):
        ctx = browser.new_context(viewport=VP)
        page = ctx.new_page()
        sign_in(page, "demo-br-portuguese@demo.bank")
        page.set_input_files("input[type=file]", str(CASOS / "ana-ifood.png"))
        page.get_by_placeholder("Pregunta por tu saldo, un cargo o uma queja…").fill("não reconheço estas transações") if False else page.get_by_placeholder("Pregunta por tu saldo, un cargo o una queja…").fill("não reconheço estas transações")
        page.get_by_role("button", name="Enviar").click()
        time.sleep(18.0)
        page.screenshot(path=str(OUT / "chat-pt.png"))
        page.goto(WEB + "/mis-finanzas", wait_until="networkidle")
        time.sleep(2.5)
        page.screenshot(path=str(OUT / "finanzas.png"))
        ctx.close()

    if what in ("consola", "all"):
        ctx = browser.new_context(viewport=VP)
        page = ctx.new_page()
        page.goto(WEB + "/consola", wait_until="networkidle")
        page.get_by_placeholder("Clave de operador").fill("5db85a6d326d588ab1e7e81829cf6d77856a41574355c67ac6036b01322dec6b")
        page.keyboard.press("Enter")
        time.sleep(3.0)
        items = page.get_by_role("button").filter(has_text="DEMO-MX-DUPLICATE")
        if items.count():
            items.first.click(); time.sleep(1.5)
        page.screenshot(path=str(OUT / "consola.png"))
        page.goto(WEB + "/consola/gerencia", wait_until="networkidle")
        time.sleep(2.5)
        page.screenshot(path=str(OUT / "gerencia.png"))
        ctx.close()

    browser.close()
shutil.rmtree(OUT / "tmp", ignore_errors=True)
print("done")
