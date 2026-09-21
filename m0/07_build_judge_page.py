"""M0 step 7 -- build the blind side-by-side judging page.

Reads sample.jsonl + pipeline1.jsonl + pipeline2.jsonl and produces:

  data/m0/judge.html      -- self-contained (inline CSS/JS, no external
                              resources/CDNs/fonts). Opened directly from
                              disk (file://) by the owner. For each of the
                              50 items: 3 sampled frames, caption, OCR text,
                              transcript, and both pipelines' fusion output,
                              labelled "Output X" / "Output Y" -- WHICH
                              pipeline made which is randomised per item and
                              NOT present anywhere in this file's source, so
                              opening dev tools can't de-blind it.
  data/m0/judge_key.json  -- {shortcode: {"X": "pipeline1"|"pipeline2",
                              "Y": "..."}}, the only place the mapping is
                              recorded. Kept separate so it never has to
                              ship to the browser.

Why data is embedded inline rather than fetched: a page opened via file://
cannot reliably fetch() a sibling JSON file (Chrome blocks XHR/fetch of
local files by default) -- but <img src="relative/path.jpg"> from a
file://-opened page works fine, so frames stay as relative-path <img> tags
and everything else (captions, OCR, transcript, both outputs) is embedded
as a JSON blob in a <script> tag instead.

The owner's judgements are never sent anywhere; the page's Save button
serialises them to JSON and triggers a normal browser download, which the
owner then saves as data/m0/judgements.json himself (§7: "the owner
produces these; they cannot be AI-generated" -- this page assists the
judging, it does not do it).

The page also autosaves progress to localStorage as a convenience (so
closing the tab mid-way through 50 items doesn't lose work) -- purely a
per-browser convenience, never read by anything outside the browser, and
the Save button is still required to actually produce judgements.json.
"""

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "m0" / "sample.jsonl"
PIPELINE1 = ROOT / "data" / "m0" / "pipeline1.jsonl"
PIPELINE2 = ROOT / "data" / "m0" / "pipeline2.jsonl"
JUDGE_HTML = ROOT / "data" / "m0" / "judge.html"
JUDGE_KEY = ROOT / "data" / "m0" / "judge_key.json"

MAX_FRAMES_SHOWN = 3
RANDOM_SEED = 20260919  # fixed so re-running without new data reproduces the same blinding


def load_jsonl(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return {
        json.loads(line)["shortcode"]: json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    }


def pick_frames(paths: list[str]) -> list[str]:
    """3 representative frames (first, middle, last), as paths relative to
    data/m0/ (where judge.html lives), so <img src="..."> resolves under
    file://."""
    if not paths:
        return []
    rel = [str(Path(p).relative_to(Path("data") / "m0")) for p in paths]
    if len(rel) <= MAX_FRAMES_SHOWN:
        return rel
    idxs = sorted({0, len(rel) // 2, len(rel) - 1})
    while len(idxs) < MAX_FRAMES_SHOWN:
        idxs.append(len(rel) - 1)
    return [rel[i] for i in sorted(set(idxs))[:MAX_FRAMES_SHOWN]]


def fusion_summary(output: dict | None) -> dict | None:
    if not output:
        return None
    return {
        "title": output.get("title", ""),
        "summary": output.get("summary", ""),
        "bullets": output.get("bullets", []),
        "urls": (output.get("entities") or {}).get("urls", []),
        "handles": (output.get("entities") or {}).get("handles", []),
        "titles": (output.get("entities") or {}).get("titles", []),
    }


def build_items():
    rng = random.Random(RANDOM_SEED)
    sample = load_jsonl(SAMPLE)
    p1 = load_jsonl(PIPELINE1)
    p2 = load_jsonl(PIPELINE2)

    items = []
    key = {}
    for sc, s in sample.items():
        r1 = p1.get(sc, {})
        r2 = p2.get(sc, {})
        ocr_text = "\n".join(
            x["text"] for x in (r1.get("ocr_verbatim") or []) if len(x["text"]) >= 2
        )

        out1 = fusion_summary(r1.get("fusion"))
        out2 = fusion_summary(r2.get("gemini_output"))

        # randomise which pipeline is "X" and which is "Y" for THIS item
        if rng.random() < 0.5:
            outputs = {"X": out1, "Y": out2}
            key[sc] = {"X": "pipeline1", "Y": "pipeline2"}
        else:
            outputs = {"X": out2, "Y": out1}
            key[sc] = {"X": "pipeline2", "Y": "pipeline1"}

        items.append(
            {
                "shortcode": sc,
                "kind": s.get("kind"),
                "sample_reason": s.get("sample_reason"),
                "caption": s.get("caption") or "",
                "frames": pick_frames(r1.get("sampled_frame_paths") or []),
                "ocr_text": ocr_text,
                "transcript": r1.get("transcript") or "",
                "outputs": outputs,
            }
        )
    return items, key


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>M0 Judging</title>
<style>
  :root {{
    --bg: #0f1115; --panel: #171a21; --panel2: #1e222b; --border: #2a2f3a;
    --text: #e6e8eb; --muted: #9aa3af; --accent: #5b9dff; --good: #3fbf7f;
    --partly: #d9a441; --bad: #e0554f;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont,
    "Segoe UI", sans-serif; margin: 0; padding: 0 16px 80px;
  }}
  header {{
    position: sticky; top: 0; background: var(--bg); padding: 14px 0 10px; z-index: 10;
    border-bottom: 1px solid var(--border);
  }}
  h1 {{ font-size: 18px; margin: 0 0 6px; }}
  .progress {{ color: var(--muted); font-size: 13px; }}
  .progress-bar {{ height: 6px; background: var(--panel2); border-radius: 3px; margin-top: 6px; overflow: hidden; }}
  .progress-fill {{ height: 100%; background: var(--accent); width: 0%; transition: width .2s; }}
  nav {{ display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }}
  button {{
    background: var(--panel2); color: var(--text); border: 1px solid var(--border);
    border-radius: 6px; padding: 8px 14px; font-size: 13px; cursor: pointer;
  }}
  button:hover {{ border-color: var(--accent); }}
  button.primary {{ background: var(--accent); border-color: var(--accent); color: #06121f; font-weight: 600; }}
  button.small {{ padding: 4px 10px; font-size: 12px; }}
  #jump {{ width: 56px; }}
  main {{ max-width: 980px; margin: 18px auto; }}
  .card {{ background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 16px; margin-bottom: 16px; }}
  .meta {{ color: var(--muted); font-size: 12px; margin-bottom: 10px; }}
  .frames {{ display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }}
  .frames img {{ height: 160px; border-radius: 6px; border: 1px solid var(--border); background: #000; }}
  .frames .noimg {{ color: var(--muted); font-size: 12px; padding: 8px; }}
  .evidence {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 14px; }}
  .evidence > div {{ background: var(--panel2); border-radius: 8px; padding: 10px 12px; }}
  .evidence h4 {{ margin: 0 0 6px; font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }}
  .evidence .txt {{ font-size: 13px; white-space: pre-wrap; max-height: 140px; overflow-y: auto; }}
  .caption-box {{ background: var(--panel2); border-radius: 8px; padding: 10px 12px; margin-bottom: 14px; font-size: 13px; }}
  .outputs {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
  .output {{ background: var(--panel2); border-radius: 8px; padding: 12px; border: 1px solid var(--border); }}
  .output h3 {{ margin: 0 0 8px; font-size: 14px; }}
  .output .field-label {{ color: var(--muted); font-size: 11px; text-transform: uppercase; margin-top: 8px; }}
  .output ul {{ margin: 4px 0; padding-left: 18px; font-size: 13px; }}
  .entities {{ font-size: 12px; color: var(--text); }}
  .entities .empty {{ color: var(--muted); font-style: italic; }}
  .judge-row {{ margin-top: 10px; }}
  .judge-row label {{ font-size: 12px; color: var(--muted); display: block; margin-bottom: 4px; }}
  .btn-group {{ display: flex; gap: 6px; }}
  .btn-group button {{ flex: 1; }}
  .btn-group button.active-yes {{ background: var(--good); border-color: var(--good); color: #06231a; }}
  .btn-group button.active-partly {{ background: var(--partly); border-color: var(--partly); color: #2a1d02; }}
  .btn-group button.active-no {{ background: var(--bad); border-color: var(--bad); color: #2a0a08; }}
  .toggle-row {{ display: flex; gap: 6px; margin-top: 6px; }}
  .toggle-row button.active {{ background: var(--bad); border-color: var(--bad); color: #2a0a08; }}
  textarea {{
    width: 100%; background: var(--panel); color: var(--text); border: 1px solid var(--border);
    border-radius: 6px; padding: 8px; font-size: 13px; font-family: inherit; margin-top: 10px;
    min-height: 50px; resize: vertical;
  }}
  footer {{
    position: fixed; bottom: 0; left: 0; right: 0; background: var(--panel);
    border-top: 1px solid var(--border); padding: 10px 16px; display: flex;
    justify-content: space-between; align-items: center;
  }}
  #status {{ color: var(--muted); font-size: 12px; }}
</style>
</head>
<body>
<header>
  <h1>M0 Extraction Bake-off &mdash; Blind Judging</h1>
  <div class="progress" id="progressText">Item 1 of N</div>
  <div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>
  <nav>
    <button class="small" id="prevBtn">&larr; Prev</button>
    <button class="small" id="nextBtn">Next &rarr;</button>
    <input type="number" id="jump" min="1" value="1"> <button class="small" id="jumpBtn">Go</button>
    <span style="flex:1"></span>
    <button class="small" id="clearBtn">Clear autosave</button>
  </nav>
</header>
<main id="main"></main>
<footer>
  <span id="status">0 / N judged</span>
  <button class="primary" id="saveBtn">Save judgements.json</button>
</footer>

<script>
const ITEMS = __ITEMS_JSON__;
const STORAGE_KEY = "m0_judgements_v1";

let judgements = {{}};
try {{
  const raw = localStorage.getItem(STORAGE_KEY);
  if (raw) judgements = JSON.parse(raw);
}} catch (e) {{ /* private browsing / blocked storage: fine, just no autosave */ }}

let current = 0;

function saveDraft() {{
  try {{ localStorage.setItem(STORAGE_KEY, JSON.stringify(judgements)); }} catch (e) {{}}
  updateStatus();
}}

function ensureJudgement(sc) {{
  if (!judgements[sc]) {{
    judgements[sc] = {{ subject_X: null, subject_Y: null, wrong_link_X: false, wrong_link_Y: false, note: "" }};
  }}
  return judgements[sc];
}}

function entityHtml(list) {{
  if (!list || list.length === 0) return '<span class="empty">(none)</span>';
  return list.map(v => `<div>&bull; ${{escapeHtml(v)}}</div>`).join("");
}}

function escapeHtml(s) {{
  return String(s).replace(/[&<>"']/g, c => ({{
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }}[c]));
}}

function outputHtml(label, out) {{
  if (!out) {{
    return `<div class="output"><h3>Output ${{label}}</h3><p class="entities empty">No output (pipeline failed on this item)</p></div>`;
  }}
  return `
    <div class="output">
      <h3>Output ${{label}}</h3>
      <div><strong>${{escapeHtml(out.title || "")}}</strong></div>
      <div style="margin-top:4px;">${{escapeHtml(out.summary || "")}}</div>
      <div class="field-label">Bullets</div>
      <ul>${{(out.bullets||[]).map(b => `<li>${{escapeHtml(b)}}</li>`).join("")}}</ul>
      <div class="field-label">URLs</div>
      <div class="entities">${{entityHtml(out.urls)}}</div>
      <div class="field-label">Handles</div>
      <div class="entities">${{entityHtml(out.handles)}}</div>
      <div class="field-label">Titles</div>
      <div class="entities">${{entityHtml(out.titles)}}</div>
    </div>`;
}}

function render() {{
  const item = ITEMS[current];
  const j = ensureJudgement(item.shortcode);
  document.getElementById("progressText").textContent =
    `Item ${{current+1}} of ${{ITEMS.length}} &mdash; ${{item.shortcode}} (${{item.kind}}, ${{item.sample_reason}})`.replace("&mdash;","—");
  document.getElementById("progressFill").style.width = `${{Math.round((current)/(ITEMS.length-1||1)*100)}}%`;
  document.getElementById("jump").value = current + 1;

  const framesHtml = item.frames.length
    ? item.frames.map(f => `<img src="${{f}}" loading="lazy">`).join("")
    : '<div class="noimg">(no frames)</div>';

  document.getElementById("main").innerHTML = `
    <div class="card">
      <div class="meta">${{item.shortcode}} &middot; ${{item.kind}} &middot; sampled for: ${{item.sample_reason}}</div>
      <div class="frames">${{framesHtml}}</div>
      <div class="caption-box"><div class="field-label" style="margin-bottom:4px;">Caption</div>${{escapeHtml(item.caption) || '<span class="entities empty">(empty)</span>'}}</div>
      <div class="evidence">
        <div><h4>OCR text (verbatim)</h4><div class="txt">${{escapeHtml(item.ocr_text) || '(none)'}}</div></div>
        <div><h4>Speech transcript</h4><div class="txt">${{escapeHtml(item.transcript) || '(none / no speech detected)'}}</div></div>
      </div>
      <div class="outputs">
        ${{outputHtml("X", item.outputs.X)}}
        ${{outputHtml("Y", item.outputs.Y)}}
      </div>

      <div class="judge-row">
        <label>Does Output X name the subject?</label>
        <div class="btn-group" data-field="subject_X">
          <button data-val="yes">Yes</button><button data-val="partly">Partly</button><button data-val="no">No</button>
        </div>
      </div>
      <div class="judge-row">
        <label>Does Output Y name the subject?</label>
        <div class="btn-group" data-field="subject_Y">
          <button data-val="yes">Yes</button><button data-val="partly">Partly</button><button data-val="no">No</button>
        </div>
      </div>
      <div class="judge-row">
        <label>Wrong / fabricated URL or handle?</label>
        <div class="toggle-row">
          <button data-toggle="wrong_link_X">Wrong in X</button>
          <button data-toggle="wrong_link_Y">Wrong in Y</button>
        </div>
      </div>
      <textarea id="noteBox" placeholder="Free-text note (optional)">${{escapeHtml(j.note||"")}}</textarea>
    </div>
  `;

  document.querySelectorAll(".btn-group").forEach(group => {{
    const field = group.dataset.field;
    group.querySelectorAll("button").forEach(btn => {{
      if (j[field] === btn.dataset.val) btn.classList.add("active-" + btn.dataset.val);
      btn.onclick = () => {{
        j[field] = (j[field] === btn.dataset.val) ? null : btn.dataset.val;
        saveDraft();
        render();
      }};
    }});
  }});
  document.querySelectorAll("[data-toggle]").forEach(btn => {{
    const field = btn.dataset.toggle;
    if (j[field]) btn.classList.add("active");
    btn.onclick = () => {{
      j[field] = !j[field];
      saveDraft();
      render();
    }};
  }});
  document.getElementById("noteBox").oninput = (e) => {{
    j.note = e.target.value;
    saveDraft();
  }};
}}

function updateStatus() {{
  const judgedCount = ITEMS.filter(it => {{
    const j = judgements[it.shortcode];
    return j && (j.subject_X || j.subject_Y || j.note);
  }}).length;
  document.getElementById("status").textContent = `${{judgedCount}} / ${{ITEMS.length}} judged`;
}}

document.getElementById("prevBtn").onclick = () => {{ current = Math.max(0, current-1); render(); }};
document.getElementById("nextBtn").onclick = () => {{ current = Math.min(ITEMS.length-1, current+1); render(); }};
document.getElementById("jumpBtn").onclick = () => {{
  const n = parseInt(document.getElementById("jump").value, 10);
  if (n >= 1 && n <= ITEMS.length) {{ current = n-1; render(); }}
}};
document.getElementById("clearBtn").onclick = () => {{
  if (confirm("Clear all autosaved judgements from this browser? This cannot be undone.")) {{
    judgements = {{}};
    saveDraft();
    render();
  }}
}};
document.getElementById("saveBtn").onclick = () => {{
  const out = {{}};
  for (const it of ITEMS) {{
    out[it.shortcode] = judgements[it.shortcode] || {{ subject_X: null, subject_Y: null, wrong_link_X: false, wrong_link_Y: false, note: "" }};
  }}
  const blob = new Blob([JSON.stringify(out, null, 2)], {{type: "application/json"}});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "judgements.json";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}};

document.addEventListener("keydown", (e) => {{
  if (e.target.tagName === "TEXTAREA") return;
  if (e.key === "ArrowRight") document.getElementById("nextBtn").click();
  if (e.key === "ArrowLeft") document.getElementById("prevBtn").click();
}});

render();
updateStatus();
</script>
</body>
</html>
"""


def main():
    items, key = build_items()

    JUDGE_KEY.write_text(json.dumps(key, indent=2))
    print(f"wrote {JUDGE_KEY} ({len(key)} items)")

    # PAGE_TEMPLATE is written with doubled braces ({{ }}) as if it were an f-string or a
    # .format() template, but substitution here is plain .replace() -- so nothing ever
    # collapsed them and 130 literal `{{`/`}}` leaked into the page, breaking the whole
    # <script> block (`let judgements = {{}};` is a JS syntax error) and the CSS with it.
    # Un-double FIRST, then inject the JSON: the items JSON legitimately contains `}}`
    # sequences from nested objects, which must not be touched.
    html = PAGE_TEMPLATE.replace("{{", "{").replace("}}", "}")
    html = html.replace("__ITEMS_JSON__", json.dumps(items, ensure_ascii=False))
    html = html.replace("Item 1 of N", f"Item 1 of {len(items)}").replace(
        "0 / N judged", f"0 / {len(items)} judged"
    )
    JUDGE_HTML.write_text(html, encoding="utf-8")
    print(f"wrote {JUDGE_HTML} ({len(items)} items, {len(html)} bytes)")


if __name__ == "__main__":
    main()
