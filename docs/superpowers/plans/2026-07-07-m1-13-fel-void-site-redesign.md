# M1.13 Fel/Void Site Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the generated guide site (index + all 70 spec pages) into the Claude Design fel/void look by porting its visual language into the Python guide generator, with no engine/data changes.

**Architecture:** All output comes from `coa_meta/guide_rendering.py` (HTML/CSS/JS constants + render functions) and `coa_meta/guide_writer.py` (asset writing). The `design/*.dc.html` files are a *visual reference only* — never staged, never shipped. We edit the generator's templates and regenerate everything from the single source of truth (`spec_results`, 70 entries) with `python -m coa_meta meta --format html`. The rejected alternative (parsing rendered HTML into per-spec JS) is not used.

**Tech Stack:** Python 3 (dataclasses, argparse), vanilla client JS (no framework), CSS custom properties + `clip-path`, self-hosted WOFF2 fonts, pytest.

## Global Constraints

_Every task's requirements implicitly include this section. Values are verbatim._

- **Brand:** `CoA Codex` (header wordmark, page `<title>`). Index hero `<h1>` is `Meta Codex`.
- **Footer copyright line:** `© 2026 CoA Codex · Fan-made theorycraft tool. Not affiliated with or endorsed by Project Ascension.`
- **Repo URL:** `https://github.com/plowsters/coacodex` · **Issues URL:** `https://github.com/plowsters/coacodex/issues`
- **Index tagline:** `Class and specialization guides for Conquest of Azeroth.` (no "Player-facing").
- **Default theme:** Fel. **localStorage key:** `coa-theme` (values `fel` | `void`). Theme is applied via `data-theme` on `<html>`.
- **Fel tokens:** `--lead:#6cf06b; --lead-bright:#b7ff6a; --lead-rgb:108,240,107; --accent:#9a6bff; --accent-rgb:154,107,255; --line:rgba(108,240,107,.24)`.
- **Void tokens (`:root[data-theme="void"]`):** `--lead:#a879ff; --lead-bright:#cbb0ff; --lead-rgb:168,121,255; --accent:#6cf06b; --accent-rgb:108,240,107; --line:rgba(168,121,255,.30)`.
- **Shared tokens:** `--gold:#ffcf5c; --gold-rgb:255,207,92; --bg:#08060f; --panel-solid:rgba(14,10,23,.92); --panel-2:rgba(9,6,16,.85); --text:#f4f1fb; --muted:#a99fc4; --dim:#8b81a6`.
- **Fonts (self-hosted):** Cinzel (display), Barlow (body), JetBrains Mono (labels), served from `assets/fonts/*.woff2` via `@font-face`; `system-ui, sans-serif` remains the fallback.
- **Ember canvas** must not start when `matchMedia('(prefers-reduced-motion: reduce)').matches`.
- **No network at runtime:** `GUIDE_JS` must contain no `fetch(` or `XMLHttpRequest`.
- **Preserve behavior:** talent-tree build/level/snapshot JS, role-filter multi-select JS, `data-tooltip-id`/tooltip-catalog lookup, and all `data-tree-*` attributes are retained.
- **`design/` stays uncommitted** and is never referenced by shipped output.
- **Regeneration command:**
  ```
  python -m coa_meta meta --format html --out reports/meta \
    --entries coa_scraper/dist/coa_entries.jsonl --classes coa_scraper/dist/coa_classes.json
  ```

---

### Task 1: Rebrand, repo links, and tagline (copy pass)

De-risks the brittle string tests first and lands all naming in one reviewable unit.

**Files:**
- Modify: `coa_meta/guide_rendering.py` (`REPO_URL`/`ISSUES_URL` ~10-11, `_render_header` ~247, `_render_footer` ~257, `render_index_html` ~271, `render_spec_html` title ~309)
- Test: `tests/test_guide_rendering.py` (lines 79, 94-96), `tests/test_report_writers.py` (line 114)

**Interfaces:**
- Produces: unchanged function signatures `render_index_html(site)`, `render_spec_html(site, spec)`, `_render_header(home_href="index.html")`, `_render_footer(site)`. Only emitted strings change.

- [ ] **Step 1: Update the brittle assertions to the new intended copy**

In `tests/test_guide_rendering.py`, line 79:
```python
    assert "CoA Codex" in html
```
Lines 94-96 (inside the `for html in ...` loop):
```python
        assert "https://github.com/plowsters/coacodex" in html
        assert "https://github.com/plowsters/coacodex/issues" in html
        assert "© 2026 CoA Codex" in html
```
In `tests/test_report_writers.py`, line 114:
```python
    assert "CoA Codex" in html
```

- [ ] **Step 2: Add a test that "Player-facing" is gone and the tagline is updated**

Append to `tests/test_guide_rendering.py`:
```python
def test_index_tagline_drops_player_facing():
    html = render_index_html(_site())
    assert "Player-facing" not in html
    assert "Class and specialization guides for Conquest of Azeroth." in html
    assert "Meta Codex" in html
```

- [ ] **Step 3: Run the three tests to verify they fail**

Run: `pytest tests/test_guide_rendering.py::test_render_index_html_uses_player_facing_guide_shell tests/test_guide_rendering.py::test_pages_include_github_header_and_footer tests/test_guide_rendering.py::test_index_tagline_drops_player_facing tests/test_report_writers.py::test_markdown_and_html_include_warnings_and_theorycraft_label -v`
Expected: FAIL (old strings still emitted).

- [ ] **Step 4: Apply the copy changes in `guide_rendering.py`**

Update the module constants:
```python
REPO_URL = "https://github.com/plowsters/coacodex"
ISSUES_URL = "https://github.com/plowsters/coacodex/issues"
```
In `_render_header`, change the brand text:
```python
        f'<a class="site-brand" href="{_e(home_href)}">CoA Codex</a>'
```
In `_render_footer`, change the copyright line:
```python
        "<p>© 2026 CoA Codex · Fan-made theorycraft tool. "
        "Not affiliated with or endorsed by Project Ascension.</p>"
```
In `render_index_html`, update the `<title>`, hero heading, and tagline:
```python
        "<title>CoA Codex</title><link rel=\"stylesheet\" href=\"assets/guide.css\">"
        ...
        "<section class=\"hero\"><h1>Meta Codex</h1>"
        "<p>Class and specialization guides for Conquest of Azeroth.</p>"
```
In `render_spec_html`, update the `<title>`:
```python
        f"<title>{_e(spec.class_name)} {_e(spec.spec_name)} Guide · CoA Codex</title>"
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_guide_rendering.py tests/test_report_writers.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add coa_meta/guide_rendering.py tests/test_guide_rendering.py tests/test_report_writers.py
git commit -m "M1.13: rebrand guide site to CoA Codex, update repo links and tagline"
```

---

### Task 2: Dual Fel/Void theme (tokens, toggle, persistence)

**Files:**
- Modify: `coa_meta/guide_rendering.py` (`GUIDE_CSS` `:root` ~29-39, `GUIDE_JS` ~111, `_render_header` ~247)
- Test: `tests/test_guide_rendering.py` (lines 349-350 + new tests)

**Interfaces:**
- Produces: `<html>` gains a `data-theme` attribute at runtime; header emits a `data-theme-toggle` control with two `[data-theme-btn]` buttons (`data-theme-value="fel"`/`"void"`). `GUIDE_JS` reads/writes `localStorage["coa-theme"]` and exposes an internal `applyTheme(value)` used by the ember palette (Task 4).

- [ ] **Step 1: Update the theme-color test and add theme-behavior tests**

Replace `tests/test_guide_rendering.py` lines 348-351 body:
```python
def test_static_assets_have_fel_void_theme_and_no_network_fetch():
    assert "#6cf06b" in GUIDE_CSS          # fel lead
    assert "#a879ff" in GUIDE_CSS          # void lead
    assert ':root[data-theme="void"]' in GUIDE_CSS
    assert "fetch(" not in GUIDE_JS
```
Append:
```python
def test_header_has_theme_toggle_and_js_persists_choice():
    html = render_index_html(_site())
    assert "data-theme-toggle" in html
    assert 'data-theme-value="fel"' in html
    assert 'data-theme-value="void"' in html
    # persistence + application
    assert '"coa-theme"' in GUIDE_JS or "'coa-theme'" in GUIDE_JS
    assert "data-theme" in GUIDE_JS
    assert "localStorage" in GUIDE_JS
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_guide_rendering.py::test_static_assets_have_fel_void_theme_and_no_network_fetch tests/test_guide_rendering.py::test_header_has_theme_toggle_and_js_persists_choice -v`
Expected: FAIL.

- [ ] **Step 3: Restructure the `:root` tokens in `GUIDE_CSS`**

Replace the `:root { ... }` block (currently ~lines 29-39) with the Fel-default tokens plus a Void override:
```css
:root {
  --bg: #08060f;
  --panel-solid: rgba(14,10,23,.92);
  --panel-2: rgba(9,6,16,.85);
  --text: #f4f1fb;
  --muted: #a99fc4;
  --dim: #8b81a6;
  --gold: #ffcf5c;
  --gold-rgb: 255,207,92;
  --lead: #6cf06b;
  --lead-bright: #b7ff6a;
  --lead-rgb: 108,240,107;
  --accent: #9a6bff;
  --accent-rgb: 154,107,255;
  --line: rgba(108,240,107,.24);
  --warning: #f5c542;
  --bevel: polygon(0 13px,13px 0,calc(100% - 13px) 0,100% 13px,100% calc(100% - 13px),calc(100% - 13px) 100%,13px 100%,0 calc(100% - 13px));
  --bevel-sm: polygon(0 7px,7px 0,calc(100% - 7px) 0,100% 7px,100% calc(100% - 7px),calc(100% - 7px) 100%,7px 100%,0 calc(100% - 7px));
}
:root[data-theme="void"] {
  --lead: #a879ff;
  --lead-bright: #cbb0ff;
  --lead-rgb: 168,121,255;
  --accent: #6cf06b;
  --accent-rgb: 108,240,107;
  --line: rgba(168,121,255,.30);
}
```
Then update existing rules that referenced the removed `--fel`/`--void` names to use `--lead`/`--accent` (e.g. `a { color: var(--lead); }`). Keep every other selector working against the new token names.

- [ ] **Step 4: Add the toggle control to `_render_header`**

Insert between the brand link and the GitHub link:
```python
        '<div class="theme-toggle" role="group" aria-label="Theme" data-theme-toggle>'
        '<button type="button" class="theme-btn" data-theme-btn data-theme-value="fel" aria-pressed="true">Fel</button>'
        '<button type="button" class="theme-btn" data-theme-btn data-theme-value="void" aria-pressed="false">Void</button>'
        '</div>'
```
Add matching CSS to `GUIDE_CSS` (segmented pill; active button uses `--lead`).

- [ ] **Step 5: Add theme init/toggle to `GUIDE_JS`**

Inside the top-level IIFE, before the tooltip logic:
```javascript
  const THEME_KEY = "coa-theme";
  function applyTheme(value) {
    const theme = value === "void" ? "void" : "fel";
    document.documentElement.setAttribute("data-theme", theme);
    document.querySelectorAll("[data-theme-btn]").forEach(btn => {
      btn.setAttribute("aria-pressed", String(btn.getAttribute("data-theme-value") === theme));
    });
    window.__coaTheme = theme;
    if (typeof window.__coaEmberRecolor === "function") window.__coaEmberRecolor(theme);
  }
  function initTheme() {
    let stored = "fel";
    try { stored = localStorage.getItem(THEME_KEY) || "fel"; } catch (_e) {}
    applyTheme(stored);
    document.addEventListener("click", event => {
      const btn = event.target.closest("[data-theme-btn]");
      if (!btn) return;
      const value = btn.getAttribute("data-theme-value");
      try { localStorage.setItem(THEME_KEY, value); } catch (_e) {}
      applyTheme(value);
    });
  }
  document.addEventListener("DOMContentLoaded", initTheme);
```

- [ ] **Step 6: Run tests to verify pass**

Run: `pytest tests/test_guide_rendering.py -v`
Expected: PASS (theme tests green; role-filter and tree tests still green).

- [ ] **Step 7: Commit**

```bash
git add coa_meta/guide_rendering.py tests/test_guide_rendering.py
git commit -m "M1.13: add dual Fel/Void theme tokens, header toggle, localStorage persistence"
```

---

### Task 3: Self-hosted fonts

**Files:**
- Create: `coa_meta/assets/fonts/*.woff2` (vendored binaries), `scripts/fetch_guide_fonts.py` (one-shot fetcher)
- Modify: `coa_meta/guide_rendering.py` (`GUIDE_CSS` `@font-face` + font-family usage), `coa_meta/guide_writer.py` (copy step)
- Test: `tests/test_guide_rendering.py`

**Interfaces:**
- Produces: `guide_writer.FONT_ASSET_DIR` (a `Path` to `coa_meta/assets/fonts`); `write_guide_site` copies its `*.woff2` into `<out>/assets/fonts/`. `GUIDE_CSS` references `url("fonts/<file>.woff2")`.

- [ ] **Step 1: Write the fetcher script**

Create `scripts/fetch_guide_fonts.py`:
```python
"""One-shot: download the WOFF2 files the guide CSS @font-faces into coa_meta/assets/fonts/."""
from __future__ import annotations
import re, urllib.request
from pathlib import Path

DEST = Path(__file__).resolve().parents[1] / "coa_meta" / "assets" / "fonts"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
FACES = {
    "Cinzel:wght@600;700;900": "Cinzel",
    "Barlow:wght@400;500;600;700": "Barlow",
    "JetBrains+Mono:wght@500;700": "JetBrainsMono",
}

def fetch(url: str) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA})).read()

def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    for spec, family in FACES.items():
        css = fetch(f"https://fonts.googleapis.com/css2?family={spec}&display=swap").decode("utf-8")
        for i, (weight, woff) in enumerate(re.findall(r"font-weight:\s*(\d+);[^}]*?src:\s*url\(([^)]+\.woff2)\)", css, re.S)):
            data = fetch(woff)
            out = DEST / f"{family}-{weight}.woff2"
            out.write_bytes(data)
            print("wrote", out, len(data), "bytes")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the fetcher and confirm files exist**

Run: `python scripts/fetch_guide_fonts.py && ls -1 coa_meta/assets/fonts/`
Expected: several `*.woff2` files (Cinzel-600/700/900, Barlow-400/500/600/700, JetBrainsMono-500/700). If the network is unavailable in this environment, download the same weights manually into `coa_meta/assets/fonts/` before continuing.

- [ ] **Step 3: Write the asset-copy test**

Append to `tests/test_guide_rendering.py`:
```python
def test_guide_css_defines_self_hosted_font_faces():
    assert "@font-face" in GUIDE_CSS
    assert 'url("fonts/' in GUIDE_CSS
    assert "Cinzel" in GUIDE_CSS
    assert "Barlow" in GUIDE_CSS
    assert "JetBrains Mono" in GUIDE_CSS
```
Create `tests/test_guide_fonts.py`:
```python
from pathlib import Path
from coa_meta.guide_writer import FONT_ASSET_DIR, write_guide_site
from coa_meta.reporting import MetaReportRunner, MetaRunConfig

FIXTURES = Path(__file__).parent / "fixtures"

def _report():
    return MetaReportRunner(MetaRunConfig(
        entries_path=FIXTURES / "meta_report_fixture.jsonl",
        classes_path=FIXTURES / "meta_classes.json",
        class_names=("Testclass",), top=1, beam_width=2, branch_width=2,
        require_budget_fraction=0.0,
    )).run()

def test_write_guide_site_copies_fonts(tmp_path):
    assert any(FONT_ASSET_DIR.glob("*.woff2")), "vendor fonts first (scripts/fetch_guide_fonts.py)"
    write_guide_site(_report(), tmp_path, entries_path=FIXTURES / "meta_report_fixture.jsonl")
    copied = list((tmp_path / "assets" / "fonts").glob("*.woff2"))
    assert copied, "no woff2 copied into assets/fonts/"
```

- [ ] **Step 4: Run to verify failure**

Run: `pytest tests/test_guide_rendering.py::test_guide_css_defines_self_hosted_font_faces tests/test_guide_fonts.py -v`
Expected: FAIL (`FONT_ASSET_DIR` undefined; no `@font-face`).

- [ ] **Step 5: Add `@font-face` blocks and font usage to `GUIDE_CSS`**

At the top of `GUIDE_CSS` add (one block per vendored weight; example for three):
```css
@font-face { font-family: "Cinzel"; font-weight: 700; font-display: swap; src: url("fonts/Cinzel-700.woff2") format("woff2"); }
@font-face { font-family: "Barlow"; font-weight: 400; font-display: swap; src: url("fonts/Barlow-400.woff2") format("woff2"); }
@font-face { font-family: "JetBrains Mono"; font-weight: 500; font-display: swap; src: url("fonts/JetBrainsMono-500.woff2") format("woff2"); }
```
Add a face for every file written in Step 2. Change `body { font-family: ... }` to `Barlow, system-ui, sans-serif`, headings to `Cinzel, serif`, and add a `.mono`/label rule using `"JetBrains Mono", monospace`.

- [ ] **Step 6: Add the copy step to `guide_writer.py`**

Add near the imports:
```python
FONT_ASSET_DIR = Path(__file__).parent / "assets" / "fonts"
```
In `write_guide_site`, after `js_path` is written (~line 65):
```python
    fonts_out = asset_dir / "fonts"
    if FONT_ASSET_DIR.exists():
        fonts_out.mkdir(parents=True, exist_ok=True)
        for font_file in sorted(FONT_ASSET_DIR.glob("*.woff2")):
            target = fonts_out / font_file.name
            target.write_bytes(font_file.read_bytes())
            written.append(target)
```

- [ ] **Step 7: Run tests to verify pass**

Run: `pytest tests/test_guide_rendering.py::test_guide_css_defines_self_hosted_font_faces tests/test_guide_fonts.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add coa_meta/guide_rendering.py coa_meta/guide_writer.py coa_meta/assets/fonts scripts/fetch_guide_fonts.py tests/test_guide_rendering.py tests/test_guide_fonts.py
git commit -m "M1.13: self-host Cinzel/Barlow/JetBrains Mono and copy fonts into assets/fonts"
```

---

### Task 4: Ember canvas ambient background

**Files:**
- Modify: `coa_meta/guide_rendering.py` (`GUIDE_JS`)
- Test: `tests/test_guide_rendering.py`

**Interfaces:**
- Consumes: `window.__coaTheme` and defines `window.__coaEmberRecolor(theme)` (referenced by `applyTheme` in Task 2).
- Produces: injects one fixed `<canvas data-embers>` behind content; no DOM contract other tasks depend on.

- [ ] **Step 1: Write the reduced-motion + no-network test**

Append to `tests/test_guide_rendering.py`:
```python
def test_ember_canvas_respects_reduced_motion_and_has_no_network():
    assert "prefers-reduced-motion" in GUIDE_JS
    assert "requestAnimationFrame" in GUIDE_JS
    assert "getContext" in GUIDE_JS
    assert "fetch(" not in GUIDE_JS
    assert "XMLHttpRequest" not in GUIDE_JS
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_guide_rendering.py::test_ember_canvas_respects_reduced_motion_and_has_no_network -v`
Expected: FAIL (`prefers-reduced-motion` absent from JS).

- [ ] **Step 3: Add the ember module to `GUIDE_JS`**

Inside the IIFE:
```javascript
  const FEL_PAL = [[108,240,107],[154,107,255],[255,207,92]];
  const VOID_PAL = [[168,121,255],[108,240,107],[255,207,92]];
  let emberPalette = FEL_PAL, emberParts = [], emberCanvas, emberCtx, emberRaf, emberW, emberH;
  window.__coaEmberRecolor = theme => { emberPalette = theme === "void" ? VOID_PAL : FEL_PAL; };
  function sizeEmberCanvas() {
    if (!emberCanvas) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    emberW = window.innerWidth; emberH = window.innerHeight;
    emberCanvas.width = emberW * dpr; emberCanvas.height = emberH * dpr;
    emberCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  function startEmbers() {
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    emberCanvas = document.createElement("canvas");
    emberCanvas.setAttribute("data-embers", "");
    emberCanvas.setAttribute("aria-hidden", "true");
    emberCanvas.style.cssText = "position:fixed;inset:0;width:100%;height:100%;z-index:0;pointer-events:none;";
    document.body.insertBefore(emberCanvas, document.body.firstChild);
    emberCtx = emberCanvas.getContext("2d");
    sizeEmberCanvas();
    const rnd = (a, b) => a + Math.random() * (b - a);
    const n = Math.min(74, Math.round(emberW / 17));
    emberParts = Array.from({ length: n }, () => ({ x: rnd(0, emberW), y: rnd(0, emberH), r: rnd(0.7, 2.5), vy: rnd(-0.5, -0.13), vx: rnd(-0.15, 0.15), a: rnd(0.14, 0.66), tw: rnd(0.004, 0.02), ph: rnd(0, 6.28), ci: Math.random() < 0.12 ? 2 : (Math.random() < 0.4 ? 1 : 0) }));
    const loop = () => {
      emberCtx.clearRect(0, 0, emberW, emberH); emberCtx.globalCompositeOperation = "lighter";
      for (const p of emberParts) {
        p.y += p.vy; p.x += p.vx; p.ph += p.tw;
        if (p.y < -10) { p.y = emberH + 10; p.x = rnd(0, emberW); }
        if (p.x < -10) p.x = emberW + 10; if (p.x > emberW + 10) p.x = -10;
        const c = emberPalette[p.ci], al = p.a * (0.55 + 0.45 * Math.sin(p.ph));
        const g = emberCtx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 4.5);
        g.addColorStop(0, "rgba(" + c[0] + "," + c[1] + "," + c[2] + "," + al + ")");
        g.addColorStop(1, "rgba(" + c[0] + "," + c[1] + "," + c[2] + ",0)");
        emberCtx.fillStyle = g; emberCtx.beginPath(); emberCtx.arc(p.x, p.y, p.r * 4.5, 0, 6.2832); emberCtx.fill();
      }
      emberCtx.globalCompositeOperation = "source-over"; emberRaf = requestAnimationFrame(loop);
    };
    loop();
    window.addEventListener("resize", sizeEmberCanvas);
  }
  document.addEventListener("DOMContentLoaded", startEmbers);
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_guide_rendering.py::test_ember_canvas_respects_reduced_motion_and_has_no_network tests/test_guide_rendering.py::test_static_tree_javascript_has_no_network_calls -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add coa_meta/guide_rendering.py tests/test_guide_rendering.py
git commit -m "M1.13: add reduced-motion-aware ember canvas that recolors with the theme"
```

---

### Task 5: Index stat line + spec-card reskin

**Files:**
- Modify: `coa_meta/guide_rendering.py` (`render_index_html` ~271, `_render_spec_card` ~338, `GUIDE_CSS`)
- Test: `tests/test_guide_rendering.py`

**Interfaces:**
- Consumes: `site.specs` (each `GuideSpec` has `.slug`, `.warning_count`, `.summary`). `_ordered_roles(site)` (existing).
- Produces: index hero contains a `data-stat-line` element; `_render_spec_card` still emits `data-role="<roles>"` so the role filter keeps working, plus a flagship badge when `spec.slug == "felsworn-tyrant"`.

- [ ] **Step 1: Write the stat-line + flagship tests**

Append to `tests/test_guide_rendering.py`:
```python
def test_index_shows_unique_spec_stat_line():
    site = _site()
    html = render_index_html(site)
    unique = len({spec.slug for spec in site.specs})
    assert "data-stat-line" in html
    assert f"{unique} spec" in html

def test_index_flagship_badge_only_on_tyrant():
    html = render_index_html(_hybrid_site())  # no tyrant -> no badge
    assert "data-flagship" not in html
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_guide_rendering.py::test_index_shows_unique_spec_stat_line tests/test_guide_rendering.py::test_index_flagship_badge_only_on_tyrant -v`
Expected: FAIL.

- [ ] **Step 3: Add the stat line in `render_index_html`**

Compute and emit it inside the hero section:
```python
    unique_specs = len({spec.slug for spec in site.specs})
    role_count = len(_ordered_roles(site))
    stat_line = (
        f'<p class="stat-line" data-stat-line>'
        f'{unique_specs} spec{"" if unique_specs == 1 else "s"} · '
        f'{role_count} role{"" if role_count == 1 else "s"}</p>'
    )
```
Insert `{stat_line}` into the hero markup after the disclaimer.

- [ ] **Step 4: Reskin `_render_spec_card` (preserve `data-role`)**

Keep the `data-role` attribute and role chips; add the flagship badge and warnings chip:
```python
def _render_spec_card(spec: GuideSpec) -> str:
    warning = '<span class="chip warning">Warnings</span>' if spec.warning_count else ""
    flagship = '<span class="flagship-badge" data-flagship>✦ Flagship</span>' if spec.slug == "felsworn-tyrant" else ""
    role_values = " ".join(_spec_roles(spec))
    return (
        f'<article class="guide-card" data-role="{_e(role_values)}">{flagship}'
        f"<h2>{_render_spec_icon(spec)} {_e(spec.class_name)} - {_e(spec.spec_name)}</h2>"
        f"<p>{_e(spec.summary)}</p><p>{_role_chips(spec)} {warning}</p>"
        f'<p><a href="{_e(spec.href)}">Open guide</a></p></article>'
    )
```
Add `.stat-line`, `.flagship-badge`, and beveled `.guide-card` styling to `GUIDE_CSS`.

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/test_guide_rendering.py -k "index or role or spec_card" -v`
Expected: PASS (new tests green; existing role-filter/grouping tests still green).

- [ ] **Step 6: Commit**

```bash
git add coa_meta/guide_rendering.py tests/test_guide_rendering.py
git commit -m "M1.13: add unique-spec stat line and reskin index cards with flagship badge"
```

---

### Task 6: Spec hero weapon/armor chip

**Files:**
- Modify: `coa_meta/guide_rendering.py` (new `_weapon_armor_chip(spec)`, called in `render_spec_html` hero ~312-314)
- Test: `tests/test_guide_rendering.py`

**Interfaces:**
- Consumes: `spec.builds[0].gear_recommendation_report` (dict with `best_weapon_types`, `available_weapon_types`, `best_armor_types`, `available_armor_types` — same keys `_render_gear_section` reads), and `spec.primary_role`/`spec.role`.
- Produces: `_weapon_armor_chip(spec) -> str` returning a `<span class="chip weapon-chip">…</span>` or `""` when no data.

- [ ] **Step 1: Write the chip tests**

Append to `tests/test_guide_rendering.py`:
```python
def test_spec_hero_renders_weapon_armor_chip_when_gear_present():
    site = _site()
    spec = next(item for item in site.specs if item.spec_name == "Damage")
    html = render_spec_html(site, spec)
    assert 'class="chip weapon-chip"' in html

def test_spec_hero_omits_weapon_chip_when_gear_empty():
    site = _hybrid_site()  # builds[0].gear_recommendation_report is empty
    spec = site.specs[0]
    html = render_spec_html(site, spec)
    assert "weapon-chip" not in html
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_guide_rendering.py::test_spec_hero_renders_weapon_armor_chip_when_gear_present tests/test_guide_rendering.py::test_spec_hero_omits_weapon_chip_when_gear_empty -v`
Expected: FAIL.

- [ ] **Step 3: Implement `_weapon_armor_chip`**

```python
def _attack_posture(spec: GuideSpec) -> str:
    role = (spec.primary_role or spec.role or "").lower()
    if role == "caster_dps":
        return "Caster"
    if role == "ranged_dps":
        return "Ranged"
    return "Melee"


def _weapon_armor_chip(spec: GuideSpec) -> str:
    build = spec.builds[0] if spec.builds else None
    report = dict(build.gear_recommendation_report or {}) if build else {}
    if not report:
        return ""
    weapons = tuple(report.get("best_weapon_types") or report.get("available_weapon_types") or ())
    armor = tuple(report.get("best_armor_types") or report.get("available_armor_types") or ())
    tokens = [_attack_posture(spec)]
    if weapons:
        tokens.append(" + ".join(dict.fromkeys(w.replace("_", " ").title() for w in weapons if w)))
    if armor:
        tokens.append(next(iter(dict.fromkeys(a.replace("_", " ").title() for a in armor if a))))
    tokens = [token for token in tokens if token]
    if len(tokens) <= 1:  # nothing but the posture guess is not worth a chip
        return ""
    return f'<span class="chip weapon-chip">{_e(" · ".join(tokens))}</span>'
```
In `render_spec_html`, append the chip after the role chips in the hero:
```python
        f'{_role_chips(spec, tooltip_id=f"role:{spec.slug}")}{_weapon_armor_chip(spec)}</section>'
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_guide_rendering.py::test_spec_hero_renders_weapon_armor_chip_when_gear_present tests/test_guide_rendering.py::test_spec_hero_omits_weapon_chip_when_gear_empty -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add coa_meta/guide_rendering.py tests/test_guide_rendering.py
git commit -m "M1.13: add hero weapon/armor chip derived from the gear report"
```

---

### Task 7: Multi-pin tooltips

**Files:**
- Modify: `coa_meta/guide_rendering.py` (`GUIDE_JS` tooltip block ~113-138, `GUIDE_CSS` `.tooltip`)
- Test: `tests/test_guide_rendering.py`

**Interfaces:**
- Consumes: existing `data-tooltip-id` attributes and `window.COA_TOOLTIPS` (unchanged).
- Produces: click-to-pin behavior on `[data-tooltip-id]`; no new server-side markup contract.

- [ ] **Step 1: Write the multi-pin behavior test**

Append to `tests/test_guide_rendering.py`:
```python
def test_tooltip_js_supports_multi_pin_and_escape():
    assert "window.COA_TOOLTIPS" in GUIDE_JS      # catalog lookup retained
    assert "Escape" in GUIDE_JS                    # esc clears
    assert "pins" in GUIDE_JS                      # stackable pins
    assert "is-pinned" in GUIDE_JS                 # gold-border class toggled
    assert 'addEventListener("scroll"' in GUIDE_JS # re-glue on scroll
    assert "fetch(" not in GUIDE_JS
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_guide_rendering.py::test_tooltip_js_supports_multi_pin_and_escape -v`
Expected: FAIL.

- [ ] **Step 3: Replace the single-tooltip block in `GUIDE_JS`**

Replace the current `active`/`showTooltip`/`removeTooltip` + `mouseover`/`mouseout` handlers with:
```javascript
  const tooltipData = window.COA_TOOLTIPS || {};
  const pins = new Map();   // id -> { el, anchor }
  let hoverEl = null, hoverAnchor = null;
  function makeTip(id, pinned) {
    const tip = tooltipData[id];
    if (!tip) return null;
    const el = document.createElement("div");
    el.className = "tooltip" + (pinned ? " is-pinned" : "");
    el.innerHTML = tip.html || tip.text || "";
    document.body.appendChild(el);
    return el;
  }
  function placeTip(el, anchor) {
    const r = anchor.getBoundingClientRect();
    el.style.left = Math.min(r.left, window.innerWidth - el.offsetWidth - 16) + "px";
    el.style.top = Math.min(r.bottom + 8, window.innerHeight - el.offsetHeight - 16) + "px";
  }
  function clearHover() { if (hoverEl) hoverEl.remove(); hoverEl = null; hoverAnchor = null; }
  function showHover(anchor) {
    const id = anchor.getAttribute("data-tooltip-id");
    if (!id || pins.has(id)) return;      // never disturb a pin
    clearHover();
    hoverEl = makeTip(id, false); hoverAnchor = anchor;
    if (hoverEl) placeTip(hoverEl, anchor);
  }
  function togglePin(anchor) {
    const id = anchor.getAttribute("data-tooltip-id");
    if (!id) return;
    if (pins.has(id)) { pins.get(id).el.remove(); pins.delete(id); return; }
    clearHover();
    const el = makeTip(id, true);
    if (!el) return;
    pins.set(id, { el, anchor }); placeTip(el, anchor);
  }
  function repositionPins() {
    pins.forEach(p => placeTip(p.el, p.anchor));
    if (hoverEl && hoverAnchor) placeTip(hoverEl, hoverAnchor);
  }
  document.addEventListener("mouseover", e => { const t = e.target.closest("[data-tooltip-id]"); if (t) showHover(t); });
  document.addEventListener("focusin", e => { const t = e.target.closest("[data-tooltip-id]"); if (t) showHover(t); });
  document.addEventListener("mouseout", e => { if (e.target.closest("[data-tooltip-id]")) clearHover(); });
  document.addEventListener("click", e => { const t = e.target.closest("[data-tooltip-id]"); if (t) togglePin(t); });
  document.addEventListener("keydown", e => { if (e.key === "Escape") { clearHover(); pins.forEach(p => p.el.remove()); pins.clear(); } });
  window.addEventListener("scroll", repositionPins, true);
  window.addEventListener("resize", repositionPins);
```
In `GUIDE_CSS`, add `.tooltip.is-pinned { border-color: var(--gold); box-shadow: 0 0 24px rgba(var(--gold-rgb),.32); }`.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_guide_rendering.py::test_tooltip_js_supports_multi_pin_and_escape tests/test_guide_rendering.py::test_static_tree_javascript_has_no_network_calls -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add coa_meta/guide_rendering.py tests/test_guide_rendering.py
git commit -m "M1.13: replace single tooltip with stackable multi-pin tooltips (Esc clears, re-glue on scroll)"
```

---

### Task 8: Leveling path — collapsible + column-major flow

**Files:**
- Modify: `coa_meta/guide_rendering.py` (`_render_leveling_path_for_build` ~707, `_render_leveling_path` ~689, `.leveling-path` CSS ~103)
- Test: `tests/test_guide_rendering.py`

**Interfaces:**
- Produces: leveling path wrapped in `<details class="leveling-path">` whose list uses a column-flow container class `leveling-list`.

- [ ] **Step 1: Write the column-flow test**

Append to `tests/test_guide_rendering.py`:
```python
def test_leveling_path_is_collapsible_and_column_major():
    site = _site()
    spec = next(item for item in site.specs if item.spec_name == "Damage")
    html = render_spec_html(site, spec)
    assert "<details" in html
    assert "Leveling Path" in html
    assert 'class="leveling-list"' in html
    assert ".leveling-list { columns:" in GUIDE_CSS   # column-major flow
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_guide_rendering.py::test_leveling_path_is_collapsible_and_column_major -v`
Expected: FAIL.

- [ ] **Step 3: Wrap the list in `<details>` with a column-flow class**

In `_render_leveling_path_for_build`, change the return to:
```python
    return (
        '<details class="leveling-path" open><summary><h3>Leveling Path</h3>'
        '<span class="mono">order to spend your essence</span></summary>'
        f'<ol class="leveling-list">{"".join(items)}</ol>{warning_html}</details>'
    )
```
Apply the same `<details>`/`leveling-list` wrapper in `_render_leveling_path` (the legacy path) for consistency.

- [ ] **Step 4: Add the column-flow CSS**

Replace the `.leveling-path { ... }` rule in `GUIDE_CSS` and add:
```css
.leveling-path { margin-top: 14px; }
.leveling-path summary { cursor: pointer; display: flex; align-items: baseline; gap: 8px; }
.leveling-list { columns: 220px auto; column-gap: 24px; list-style: none; padding: 8px 0 0; margin: 0; }
.leveling-list li { break-inside: avoid; margin-bottom: 6px; color: var(--muted); }
```
`columns: 220px auto` makes items fill each column top-to-bottom, then wrap to the next column left-to-right — the requested order.

- [ ] **Step 5: Run to verify pass (and existing leveling tests still green)**

Run: `pytest tests/test_guide_rendering.py -k leveling -v`
Expected: PASS (`test_spec_html_renders_exact_leveling_path_events`, `test_leveling_path_omits_boilerplate_reason`, and the new test).

- [ ] **Step 6: Commit**

```bash
git add coa_meta/guide_rendering.py tests/test_guide_rendering.py
git commit -m "M1.13: make leveling path collapsible and column-major (top-to-bottom, then left-to-right)"
```

---

### Task 9: Sticky section nav + panel/tree reskin

**Files:**
- Modify: `coa_meta/guide_rendering.py` (`render_spec_html` nav ~299 & panels, `_render_build`/`_render_rotation_section`/`_render_stats_section`/`_render_gear_section`/`_render_node` markup, tree CSS in `GUIDE_CSS`)
- Test: `tests/test_guide_rendering.py`

**Interfaces:**
- Consumes: existing section ids and `data-tree-*`/`data-tooltip-id` attributes.
- Produces: purely cosmetic markup/CSS; **all** existing data attributes and section ids are preserved.

- [ ] **Step 1: Write the "reskin preserves behavior" test**

Append to `tests/test_guide_rendering.py`:
```python
def test_spec_nav_is_sticky_and_tree_behavior_preserved():
    site = _site()
    spec = next(item for item in site.specs if item.spec_name == "Damage")
    html = render_spec_html(site, spec)
    assert 'class="guide-nav"' in html
    # tree data contracts intact
    assert 'data-tree-kind="ability_essence"' in html
    assert "data-tree-level-selector" in html
    assert 'class="tree-links"' in html
    # css guarantees from prior milestones still hold
    assert ".tree-scroll { overflow-x: auto" in GUIDE_CSS
    assert ".guide-nav { " in GUIDE_CSS and "position: sticky" in GUIDE_CSS
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_guide_rendering.py::test_spec_nav_is_sticky_and_tree_behavior_preserved -v`
Expected: FAIL if `.guide-nav` lacks `position: sticky` markup/CSS in the new form; otherwise adjust markup to satisfy it.

- [ ] **Step 3: Reskin panels and nav (markup/classes only)**

Restyle the section-nav (`guide-nav` already sticky — keep `position: sticky`), Recommended Builds cards, Rotation/Stats/Gear/Abilities panels, and the talent-tree node/edge/frame styling to the beveled/gold design using the theme tokens. **Do not** change any `data-*` attribute, section id, tree kind, or the `.tree-scroll { overflow-x: auto` rule. **Do not** move `talent-tree`/`tree-group`/`passive-lane` selectors into an `@media` block (guarded by `test_tree_css_keeps_desktop_geometry_and_horizontal_scroll`).

- [ ] **Step 4: Run the full rendering suite**

Run: `pytest tests/test_guide_rendering.py -v`
Expected: PASS (all reskin + all preserved-behavior tests green).

- [ ] **Step 5: Commit**

```bash
git add coa_meta/guide_rendering.py tests/test_guide_rendering.py
git commit -m "M1.13: reskin spec-page nav, panels, and talent tree to the fel/void design"
```

---

### Task 10: Full regeneration and end-to-end verification

**Files:**
- No source changes (verification only). Output: `reports/meta/**` regenerated.

- [ ] **Step 1: Run the entire test suite**

Run: `pytest`
Expected: PASS (no regressions across guide, report-writer, builder, tooltip, tree, leveling suites).

- [ ] **Step 2: Regenerate the full site**

Run:
```bash
python -m coa_meta meta --format html --out reports/meta \
  --entries coa_scraper/dist/coa_entries.jsonl --classes coa_scraper/dist/coa_classes.json
```
Expected: exit 0; `reports/meta/index.html`, `reports/meta/specs/*.html` (70 pages), `reports/meta/assets/guide.css`, `guide.js`, and `reports/meta/assets/fonts/*.woff2` all present.

- [ ] **Step 3: Verify the assets landed**

Run: `ls reports/meta/assets/fonts/ && grep -c "@font-face" reports/meta/assets/guide.css && grep -l "CoA Codex" reports/meta/index.html`
Expected: woff2 files listed; `@font-face` count > 0; index matches `CoA Codex`.

- [ ] **Step 4: Manual browser check (use the /run or /verify skill, or open directly)**

Open `reports/meta/index.html` and `reports/meta/specs/felsworn-tyrant.html` plus one healer, one caster, one support, and one ranged spec. Confirm:
  - Fel/Void toggle works and the choice **persists** when navigating index → spec → back.
  - Self-hosted fonts render (Cinzel headings, Barlow body); Network tab shows fonts loading from `assets/fonts/`, not Google.
  - Ember canvas animates; with OS "reduce motion" on, it does not start.
  - Multi-pin: hover a node shows a tooltip; clicking pins it (gold border); pinning a second keeps the first; clicking a pin again unpins just it; Esc clears all; pins stay glued to nodes while scrolling.
  - Leveling path reads top-to-bottom down each column, then left-to-right.
  - Hero weapon/armor chip shows for specs with gear data; footer says `© 2026 CoA Codex`; tagline has no "Player-facing".

- [ ] **Step 5: Confirm `design/` is still uncommitted**

Run: `git status --short design/`
Expected: files show as untracked/modified (never staged). Do not stage them.

- [ ] **Step 6: Commit the regenerated report output**

```bash
git add reports/meta
git commit -m "M1.13: regenerate guide site with fel/void redesign"
```

---

## Self-Review

**Spec coverage:** Theme system → Task 2; self-hosted fonts → Task 3; ember canvas → Task 4; header/footer/naming/repo links → Task 1; index tagline + stat line + card reskin → Tasks 1 & 5; spec hero + weapon chip → Task 6; section nav + panel/tree reskin → Task 9; multi-pin tooltips → Task 7; leveling collapsible + column-major → Task 8; test updates → every task; regeneration + `design/` uncommitted + all-70 coverage → Task 10. All spec sections map to a task.

**Placeholder scan:** No "TBD"/"handle edge cases"/"similar to Task N" — each code step shows concrete code. Task 9's reskin is described as markup/CSS-only with explicit preservation constraints and is gated by concrete behavior-preservation assertions rather than snapshotting.

**Type/name consistency:** `applyTheme`/`window.__coaEmberRecolor`/`window.__coaTheme` are defined in Task 2 and consumed in Task 4; `FONT_ASSET_DIR` defined in Task 3 and used by its test; `_weapon_armor_chip`/`_attack_posture` defined and called in Task 6; `leveling-list` class defined in Task 8 markup and asserted in its test; `data-theme`/`coa-theme` consistent across Tasks 2 and 10. Existing preserved contracts (`data-tree-kind`, `data-tooltip-id`, `.tree-scroll { overflow-x: auto`, `selected.has(clicked)`, `selected.size === 0`) are asserted, not broken.
