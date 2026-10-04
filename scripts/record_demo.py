"""Record the demo video: a captioned walkthrough of the running app, saved as MP4.

Usage (with the app running at http://localhost:8501, your resume uploaded and jobs scored):
  python scripts/record_demo.py [--url URL] [--out FILE]

Needs Playwright's Chromium (`python -m playwright install chromium`) and ffmpeg on PATH.
The walkthrough presses Save on one job; every status it changes is put back afterwards.
The video shows your own resume and jobs, so it is written outside the repository
(default: <docs_dir>/demo/jobhunt-ai-demo.mp4).
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

W, H = 1280, 760
FADE = 0.5  # seconds of crossfade between steps
CAPTION_JS = """(text) => { let d = document.getElementById('demo-caption');
  if (!d) { d = document.createElement('div'); d.id = 'demo-caption'; document.body.appendChild(d); }
  d.textContent = text;
  d.style.cssText = 'position:fixed;left:50%;bottom:22px;transform:translateX(-50%);z-index:99999;' +
    'background:#0f172a;color:#fff;font:600 17px "Segoe UI",sans-serif;padding:10px 18px;border-radius:6px;' +
    'box-shadow:0 4px 14px rgba(15,23,42,.25);max-width:80%;text-align:center;'; }"""
IDLE_JS = ("() => { const a = document.querySelector('[data-testid=stApp]');"
           " return a && a.getAttribute('data-test-script-state') === 'notRunning'; }")


class Walkthrough:
    def __init__(self, page, folder: Path) -> None:
        self.page, self.folder, self.steps = page, folder, []

    def settle(self, extra: float = 0.8) -> None:
        """Wait until Streamlit has finished rerunning the script."""
        self.page.wait_for_timeout(500)
        self.page.wait_for_function(IDLE_JS, timeout=180_000)
        self.page.wait_for_timeout(int(extra * 1000))

    def shot(self, caption: str, hold: float) -> None:
        self.page.evaluate(CAPTION_JS, caption)
        path = self.folder / f"{len(self.steps):02d}.png"
        self.page.screenshot(path=str(path))
        self.steps.append((path, hold))
        self.page.evaluate("() => document.getElementById('demo-caption')?.remove()")

    def scroll(self, dy: int) -> None:
        self.page.mouse.move(W * 0.6, H * 0.5)
        self.page.mouse.wheel(0, dy)
        self.page.wait_for_timeout(900)

    def scroll_to(self, text: str) -> None:
        self.visible_text(text).scroll_into_view_if_needed()
        self.page.wait_for_timeout(600)

    def visible_text(self, text: str):
        return self.page.get_by_text(text).locator("visible=true").first

    def run(self, url: str) -> None:
        pg = self.page
        pg.goto(url)
        pg.wait_for_selector("[role=tab]", timeout=60_000)
        self.settle(1.5)
        tabs = pg.locator("[role=tab]")
        self.shot("JobHunt AI: your numbers and the next step, above everything", 4)
        self.scroll(330)
        self.shot("Resume: the skills it found, plus any you add by hand", 4)

        self.scroll(-9000); tabs.nth(1).click(); self.settle()
        self.shot("Find jobs: collect postings from free job APIs, politely", 4)
        self.visible_text("Back up or clean up stored jobs").click(); self.settle()
        self.scroll_to("Delete jobs older than")
        self.shot("Back up jobs and scores as CSV, clear out old postings", 4)

        self.scroll(-9000); tabs.nth(2).click(); self.settle()
        self.shot("Matches: every job scored against your resume", 4)
        search = pg.get_by_placeholder("Title, company, location or skill").locator("visible=true").first
        search.click(); search.type("java", delay=60); search.press("Enter"); self.settle()
        self.scroll(380)
        self.shot("Search and filter: strong, possible or weak, with the skills you have and lack", 4.5)
        self.visible_text("Charts for the jobs shown").click(); self.settle()
        self.scroll_to("Where the jobs came from"); self.scroll(-120)
        self.shot("Charts for the jobs on screen", 3.5)
        self.visible_text("Charts for the jobs shown").click(); self.settle()
        self.visible_text("Score breakdown, skills and full posting").click(); self.settle()
        self.scroll_to("Skills and keywords"); self.scroll(-60)
        self.shot("Why a job scores the way it does, and the must-have skills", 4.5)
        self.visible_text("Show the full job description").click(); self.settle()
        self.scroll_to("Show the full job description"); self.scroll(200)
        self.shot("The full posting, formatted for reading", 4)
        self.scroll(-9000); self.settle(0.3)
        save = pg.get_by_role("button", name="Save", exact=True).locator("visible=true").first
        save.scroll_into_view_if_needed(); save.click(); self.settle(0.6)
        self.shot("Save the jobs worth applying to", 3)

        self.scroll(-9000); tabs.nth(3).click(); self.settle()
        self.shot("Applications: everything saved, applied to or rejected, in one place", 4)
        pg.get_by_role("button", name="Write documents").locator("visible=true").first.click(); self.settle()
        tabs.nth(4).click(); self.settle()
        self.shot("Documents: a cover letter for that job, exported as .txt, .docx or .pdf", 4.5)


def stitch(steps: list, dest: Path) -> None:
    """Join the screenshots into an MP4, each held for its time, with short crossfades."""
    args = ["ffmpeg", "-loglevel", "error", "-y"]
    for path, hold in steps:
        args += ["-loop", "1", "-t", str(hold + FADE), "-i", str(path)]
    parts, offset, prev = [], 0.0, "[0:v]"
    for i in range(1, len(steps)):
        offset += steps[i - 1][1]
        parts.append(f"{prev}[{i}:v]xfade=transition=fade:duration={FADE}:offset={offset:.2f}[v{i}]")
        prev = f"[v{i}]"
    args += ["-filter_complex", ";".join(parts), "-map", prev, "-r", "30", "-c:v", "libx264",
             "-pix_fmt", "yuv420p", "-crf", "24", "-movflags", "+faststart", str(dest)]
    subprocess.run(args, check=True)


def _statuses() -> dict:
    from db import repository as repo

    resume = repo.latest_resume()
    return {m["id"]: m["status"] for m in repo.list_matches(resume["id"], limit=1000)} if resume else {}


def _restore(before: dict) -> int:
    from db import repository as repo

    changed = {mid: status for mid, status in before.items() if _statuses().get(mid) != status}
    for mid, status in changed.items():
        repo.update_match_status(mid, status)
    return len(changed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://localhost:8501")
    parser.add_argument("--out", default=None, help="MP4 to write (default: <docs_dir>/demo/jobhunt-ai-demo.mp4)")
    args = parser.parse_args(argv)
    if not shutil.which("ffmpeg"):
        print("ffmpeg is not on PATH. Install it (winget install Gyan.FFmpeg) and try again.")
        return 1
    from playwright.sync_api import sync_playwright

    from config import get_settings

    dest = Path(args.out) if args.out else Path(get_settings().docs_dir).expanduser() / "demo" / "jobhunt-ai-demo.mp4"
    dest.parent.mkdir(parents=True, exist_ok=True)
    before = _statuses()
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            walk = Walkthrough(browser.new_page(viewport={"width": W, "height": H}), Path(tmp))
            walk.run(args.url)
        finally:
            browser.close()
            restored = _restore(before)
        stitch(walk.steps, dest)
    print(f"Wrote {dest} ({len(walk.steps)} steps). Put back {restored} job status(es) the walkthrough changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
