"""The shared presentation system must work without theme-specific patches."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.pptx_test_support import skip_unavailable_pptx_runtime

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "box_agent/skills/document-skills/pptx"
NODE = os.environ.get("BOX_AGENT_NODE") or shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is required")


def node(code: str, *args: str) -> dict:
    result = subprocess.run([str(NODE), "-e", code, str(SKILL), *map(str, args)], text=True, capture_output=True, check=False)
    skip_unavailable_pptx_runtime(result)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def run(script: str, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run([str(NODE), str(SKILL / "scripts" / script), *map(str, args)], text=True, capture_output=True, check=False)
    skip_unavailable_pptx_runtime(result)
    return result


def test_all_themes_and_layouts_inherit_one_presentation_contract():
    data = node(r'''
const path=require('path'),root=process.argv[1],core=require(path.join(root,'scripts/deck_spec_core.js')),reg=require(path.join(root,'layouts/registry.js')),system=require(path.join(root,'runtime/presentation-system.js')),matrix=require(path.join(root,'scripts/render_theme_matrix.js'));
const themes=core.listThemes();console.log(JSON.stringify({issues:matrix.checkContracts(themes),themes:themes.length,layouts:reg.layouts.length,presentations:themes.map(t=>core.themeManifestRecord(t).presentation),compositions:reg.layouts.map(l=>system.preferredComposition(l))}));
''')
    assert not data["issues"]
    assert data["themes"] >= 52 and data["layouts"] >= 33
    assert all(p["version"] == 1 and p["voice"] for p in data["presentations"])
    assert all(data["compositions"])


def test_density_depends_on_content_and_does_not_mutate_it():
    data = node(r'''
const path=require('path'),root=process.argv[1],r=require(path.join(root,'layouts/registry.js')),s=require(path.join(root,'runtime/presentation-system.js'));
const layout=r.getLayout('cards-grid-v1'),props=r.createEditorProps(layout.id),before=JSON.stringify(props),short=s.measureContent(props,layout.fields),stable=before===JSON.stringify(props);
props.title='信息完整性与内容容量检查'.repeat(4);props.items=Array.from({length:6},()=>({title:'需要完整保留的业务要求'.repeat(3),body:'针对关键场景明确边界并保留全部信息。'.repeat(5)}));
console.log(JSON.stringify({short,stable,long:s.measureContent(props,layout.fields)}));
''')
    assert data["short"]["density"] == "sparse"
    assert data["long"]["density"] == "dense"
    assert data["stable"]


def test_future_theme_inherits_geometry_colors_and_sketch_without_id_css(tmp_path):
    html_path = tmp_path / "future.html"
    data = node(r'''
const fs=require('fs'),path=require('path'),root=process.argv[1],core=require(path.join(root,'scripts/deck_spec_core.js')),matrix=require(path.join(root,'scripts/render_theme_matrix.js')),render=require(path.join(root,'scripts/render_deck_html.js')),reg=require(path.join(root,'layouts/registry.js'));
const theme=structuredClone(core.getTheme('sketch-whiteboard'));theme.id='future-workshop-brand';theme.name='Future workshop';theme.selection.visual_dna_ids=[theme.id];theme.palette.primary='#5C486C';theme.palette.primary_soft='#EAE4EF';
const chosen=['cards-grid-v1','timeline-horizontal-v1','closing-next-steps-v1'].map(id=>reg.getLayout(id));const deck=matrix.previewDeck(theme,chosen);fs.writeFileSync(process.argv[2],render.renderDocument(deck,theme));console.log(JSON.stringify({issues:matrix.checkContracts([theme],chosen)}));
''', html_path)
    assert not data["issues"]
    html = html_path.read_text()
    assert 'data-deck-voice="sketch"' in html
    assert 'data-deck-runtime="sketch-runtime"' in html
    assert 'data-presentation-density="sparse"' in html
    qa = tmp_path / "qa.json"
    result = run("html_self_check.js", html_path, "--report", qa)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not json.loads(qa.read_text())["warnings"]
    runtime = tmp_path / "runtime.json"
    result = run("probe_deck_runtime.js", html_path, "--report", runtime)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(runtime.read_text())["editor"]["componentContrast"]["failureCount"] == 0


def test_new_theme_styles_are_validated_and_presentation_css_has_no_theme_id_rules():
    data = node(r'''
const path=require('path'),root=process.argv[1],c=require(path.join(root,'scripts/deck_spec_core.js')),m=require(path.join(root,'scripts/render_theme_matrix.js'));const t=structuredClone(c.getTheme('blue-professional'));t.id='future';t.style.heading='unregistered-heading';console.log(JSON.stringify({issues:m.checkContracts([t])}));
''')
    assert any("future.style.heading" in issue for issue in data["issues"])
    css = (SKILL / "runtime/presentation-system.css").read_text()
    assert "data-deck-theme=" not in css and "data-deck-theme-id=" not in css


@pytest.mark.parametrize("overflow", [False, True])
def test_qa_distinguishes_internal_connector_overflow_from_clipped_text(tmp_path, overflow):
    html = tmp_path / "index.html"
    content = "正文必须保持完整，不能被裁掉。" * (60 if overflow else 1)
    html.write_text(f'''<!doctype html><html><style>.slide{{width:1920px;height:1080px;position:relative;box-sizing:border-box}}.node{{position:absolute;left:100px;top:100px;width:400px;height:180px;padding:20px;border:1px solid;font:24px/1.5 sans-serif;box-sizing:border-box}}.node::after{{content:"";position:absolute;right:-30px;top:30px;width:24px;height:24px;border:2px solid}}</style><section class="slide"><div class="node">{content}</div></section></html>''')
    qa = tmp_path / "qa.json"
    run("html_self_check.js", html, "--report", qa)
    report = json.loads(qa.read_text())
    warnings = report["issues"] + report["warnings"]
    assert any("text/content overflow" in warning for warning in warnings) is overflow


def test_shared_palette_can_supply_accessible_text_on_middle_gray():
    result = node(r'''
const path=require('path'),m=require(path.join(process.argv[1],'scripts/design_contract_core.js'));const color=m.readableForeground('#777777','#888888');console.log(JSON.stringify({color,contrast:m.contrastRatio(color,'#777777')}));
''')
    assert result["contrast"] >= 4.5


def test_editor_recomputes_density_and_preserves_saved_content(tmp_path):
    html = tmp_path / "index.html"
    node(r'''
const fs=require('fs'),path=require('path'),root=process.argv[1],core=require(path.join(root,'scripts/deck_spec_core.js')),matrix=require(path.join(root,'scripts/render_theme_matrix.js')),reg=require(path.join(root,'layouts/registry.js')),render=require(path.join(root,'scripts/render_deck_html.js'));
const theme=core.getTheme('sketch-whiteboard'),deck=matrix.previewDeck(theme,[reg.getLayout('cards-grid-v1')]);fs.writeFileSync(process.argv[2],render.renderDocument(deck,theme));console.log('{}');
''', html)
    result = node(r'''
const fs=require('fs'),path=require('path'),os=require('os'),Module=require('module'),{pathToFileURL}=require('url'),root=process.argv[1],host=require(path.join(root,'scripts/playwright_host.js'));host.ensurePlaywrightBrowsersPath();
const prefix=process.env.BOX_AGENT_NODE_PREFIX||process.env.BOX_AGENT_RUNTIME_PREFIX||(process.platform==='darwin'?path.join(os.homedir(),'Library/Application Support/office-raccoon'):process.platform==='win32'?path.join(process.env.APPDATA||os.homedir(),'office-raccoon'):path.join(os.homedir(),'.config/office-raccoon'));process.env.NODE_PATH=[path.join(prefix,'node_modules'),process.env.NODE_PATH].filter(Boolean).join(path.delimiter);Module._initPaths();const{chromium}=require('playwright');
(async()=>{const b=await chromium.launch(host.chromiumLaunchOptions(chromium,{headless:true}).options);try{const p=await b.newPage({viewport:{width:1440,height:900}});await p.addInitScript(()=>Object.defineProperty(navigator,'webdriver',{configurable:true,get:()=>false}));await p.goto(pathToFileURL(process.argv[2]).href);await p.evaluate(()=>window.__deckTextReady);
const state=()=>p.evaluate(()=>({concepts:document.querySelectorAll('#deck-root [data-sketch-role="concept-circle"]').length,density:document.querySelector('#deck-root > .slide').dataset.presentationDensity,font:parseFloat(getComputedStyle(document.querySelector('#deck-root .open-point-body')).fontSize),document:window.__deckRuntime.getDocument()}));const before=await state();await p.locator('[data-action="edit"]').click();const body=p.locator('#deck-root .open-point-body').first();const text='围绕关键使用场景记录观察证据并明确下一次验证的边界。'.repeat(3);await body.fill(text);await body.press('Tab');const after=await state();const save=path.join(path.dirname(process.argv[2]),'saved.html');fs.writeFileSync(save,await p.evaluate(()=>window.__deckRuntime.serializeHtml()));await p.goto(pathToFileURL(save).href);await p.evaluate(()=>window.__deckTextReady);const reopened=await state();console.log(JSON.stringify({before,after,reopened,text}));}finally{await b.close()}})().catch(e=>{console.error(e);process.exit(1)});
''', html)
    assert result["before"]["density"] == "sparse"
    assert result["before"]["concepts"] > 0
    assert result["after"]["density"] != "sparse"
    assert result["after"]["font"] < result["before"]["font"]
    assert result["after"]["document"] == result["reopened"]["document"]
    assert result["after"]["document"]["slides"][0]["props"]["items"][0]["body"] == result["text"]
    assert result["reopened"]["density"] == result["after"]["density"]


def test_matrix_automatically_includes_a_new_registered_layout():
    result = node(r'''
const path=require('path'),root=process.argv[1],reg=require(path.join(root,'layouts/registry.js')),core=require(path.join(root,'scripts/deck_spec_core.js')),matrix=require(path.join(root,'scripts/render_theme_matrix.js'));
const source=reg.getLayout('cards-grid-v1'),extra={...source,id:'future-parallel-layout',editor:{...source.editor,label:'未来新增布局'}};reg.layouts.push(extra);
const theme=core.getTheme('blue-professional'),deck=matrix.previewDeck(theme);const validated=core.validateAndNormalizeDeck(deck);console.log(JSON.stringify({count:deck.slides.length,last:deck.slides.at(-1),valid:validated.ok,issues:validated.issues,contracts:matrix.checkContracts([theme])}));
''')
    assert result["valid"], result["issues"]
    assert not result["contracts"]
    assert result["last"]["layout_id"] == "future-parallel-layout"
    assert result["last"]["props"]["composition"] == "open"
    assert result["count"] >= 34


def test_short_copy_balances_lines_without_orphan_character(tmp_path):
    html = tmp_path / "copy.html"
    node(r'''
const fs=require('fs'),path=require('path'),root=process.argv[1],core=require(path.join(root,'scripts/deck_spec_core.js')),matrix=require(path.join(root,'scripts/render_theme_matrix.js')),reg=require(path.join(root,'layouts/registry.js')),render=require(path.join(root,'scripts/render_deck_html.js'));const theme=core.getTheme('blue-professional'),deck=matrix.previewDeck(theme,[reg.getLayout('cards-grid-v1')]);fs.writeFileSync(process.argv[2],render.renderDocument(deck,theme));console.log('{}');
''', html)
    report = tmp_path / "qa.json"
    result = run("html_self_check.js", html, "--report", report)
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(report.read_text())
    subtitle = next(t for t in data["typography"] if t["path"] == "subtitle")
    assert subtitle["state"] == "fit"
    assert len(subtitle["lines"][-1].strip("。 ，")) >= 2
    assert "".join(subtitle["lines"]) == "并列讨论产品、服务和协作三个方向。"


def test_export_qa_accepts_native_table_padding_but_still_flags_badges(tmp_path):
    html = tmp_path / "table.html"
    html.write_text('''<!doctype html><html><style>.slide{width:1920px;height:1080px;position:relative}table{position:absolute;left:100px;top:100px}th,td{padding:20px;background:#183C56;color:white}.badge{position:absolute;left:100px;top:500px;padding:20px;background:#183C56;color:white}</style><section class="slide"><table><tr><th>PASS</th><td>READY</td></tr></table><div class="badge">PASS</div></section></html>''')
    qa = tmp_path / "qa.json"
    run("html_self_check.js", html, "--dom-to-pptx", "--report", qa)
    warnings = json.loads(qa.read_text())["warnings"]
    padding = [w for w in warnings if "short background text uses vertical padding" in w]
    assert len(padding) == 1
    assert "div.badge" in padding[0]


def test_brief_triples_earn_a_larger_scale_only_with_header_room():
    result = node(r'''
const path=require('path'),root=process.argv[1],r=require(path.join(root,'layouts/registry.js')),s=require(path.join(root,'runtime/presentation-system.js'));const l=r.getLayout('cards-grid-v1'),p=r.createEditorProps(l.id);p.items=[{title:'事实',body:'已观察现象'},{title:'猜测',body:'未验证解释'},{title:'方案',body:'准备尝试动作'}];const brief=s.measureContent(p,l.fields);p.subtitle='说明文字占据更多空间，需要给主体保留实际可用的空间。'.repeat(4);const longHeader=s.measureContent(p,l.fields);console.log(JSON.stringify({brief,longHeader}));
''')
    assert result["brief"]["briefItems"]
    assert not result["longHeader"]["briefItems"]


def test_matrix_rejects_theme_ids_that_escape_its_output_directory():
    result = node(r'''
const path=require('path'),root=process.argv[1],core=require(path.join(root,'scripts/deck_spec_core.js')),matrix=require(path.join(root,'scripts/render_theme_matrix.js'));const theme=structuredClone(core.getTheme('blue-professional'));theme.id='../outside';console.log(JSON.stringify({issues:matrix.checkContracts([theme])}));
''')
    assert any("path separators" in issue for issue in result["issues"])
