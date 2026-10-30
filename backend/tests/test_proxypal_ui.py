import json
import os
from pathlib import Path
from urllib.parse import quote

import pytest
from playwright.sync_api import expect, sync_playwright

# Mocked tests run against the Vite dev server; the live test can target the built app.
URL = os.environ.get('PROXYPAL_UI_URL', 'http://localhost:5173')
ROOT = Path(__file__).resolve().parents[2]


def live_url():
    """The live test must authenticate like the browser does when the gateway requires a token."""
    stored = ROOT / 'data' / '.gateway_token'
    token = stored.read_text(encoding='utf-8').strip() if stored.exists() else ''
    if not token:
        token = os.environ.get('GATEWAY_TOKEN', '').strip()
    if not token:
        return URL
    return URL + ('&' if '?' in URL else '?') + 'token=' + quote(token)


@pytest.fixture(scope='module')
def browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    page = context.new_page()
    yield page
    context.close()


MOCK_SCRIPT = r"""
(() => {
  const original = window.fetch.bind(window);
  const key = (id, label, state, percent, provider='groq') => ({id, label, provider, masked_key:'••••test',
    enabled:true, state, tokens:percent*10, reported_tokens:percent*10, estimated_tokens:0,
    requests:1, token_budget:1000, request_budget:100, token_percent:percent, request_percent:1,
    threshold:.9, cooldown_until:0, rate_limits:{}});
  const pool = {keys:[key('ui-a','اختبار A','active',89),key('ui-b','اختبار B','standby',0),
    {...key('ui-off','معطّل','disabled',0,'other'),enabled:false}],
    active_id:'ui-a', next_id:'ui-b', switch_count:12, scope:'local_budget', strategy:'sticky'};
  const providers = [{provider:'groq',models:['model-a','model-b','model-c'],key_count:2,custom:false,
    base_url:'https://api.groq.com/openai/v1'},
    {provider:'other',models:['ghost-model'],key_count:1,custom:false,base_url:'https://other.test/v1'}];
  const health = {'model-a':{ok:true,at:Math.floor(Date.now()/1000),latency_ms:120}};
  window.uiTest = {calls:[], probes:[], speech:[], cancelled:0, pool, health, auth:[], refreshes:0};
  if (window.speechSynthesis) {
    window.speechSynthesis.speak = utterance => window.uiTest.speech.push({text:utterance.text,lang:utterance.lang});
    window.speechSynthesis.cancel = () => {window.uiTest.cancelled++};
  }
  const json = data => new Response(JSON.stringify(data), {headers:{'Content-Type':'application/json'}});
  const status = () => ({version:6,providers,pool,model_health:health});
  window.fetch = async (url, options={}) => {
    window.uiTest.auth.push((options.headers || {}).Authorization || null);
    if (String(url).includes('/status')) return json(status());
    if (String(url).includes('/workspace/root')) return json({root:'/workspace'});
    if (String(url).includes('/workspace/snapshot')) return json({root:'/workspace',
      files:[{path:'main.py',content:'print(1)'}]});
    if (String(url).includes('/settings')) {
      const body = JSON.parse(options.body || '{}');
      pool.strategy = body.strategy || pool.strategy;
      return json(status());
    }
    if (String(url).includes('/pool/providers')) {
      const body = JSON.parse(options.body || '{}');
      const nameOf = () => decodeURIComponent(String(url).split('/pool/providers/')[1].replace('/models', ''));
      if (options.method === 'DELETE') {
        const name = nameOf();
        const index = providers.findIndex(item => item.provider === name);
        if (index >= 0) providers.splice(index, 1);
        pool.keys = pool.keys.filter(item => item.provider !== name);
        if (!pool.keys.some(item => item.id === pool.active_id)) pool.active_id = (pool.keys[0] || {}).id || null;
        return json(status());
      }
      if (options.method === 'PATCH') {
        const target = providers.find(item => item.provider === nameOf());
        if (target) target.models = body.models;
        return json(status());
      }
      providers.push({provider:body.name, models:body.models, key_count:0, custom:true, base_url:body.base_url});
      return json(status());
    }
    if (String(url).endsWith('/pool/keys') && options.method === 'POST') {
      const body = JSON.parse(options.body || '{}');
      const invalid = body.api_keys.filter(item => item.startsWith('bad')).length;
      const valid = body.api_keys.length - invalid;
      for (let index = 0; index < valid; index++)
        pool.keys.push(key('new-'+Date.now()+'-'+index, 'مفتاح جديد', 'standby', 0, body.provider));
      return json({...status(), validation:{added:valid, rejected:invalid, unverified:0}});
    }
    if (String(url).includes('/models/refresh')) {
      window.uiTest.refreshes++;
      providers[0].models = ['model-a','model-b','model-new'];
      health['model-b'] = {ok:false, at:Math.floor(Date.now()/1000), reason:'upstream', status:404, latency_ms:80};
      health['model-new'] = {ok:true, at:Math.floor(Date.now()/1000), latency_ms:90};
      return json({...status(), refresh:{probed:3, ok:2, failed:1, skipped:0, deadline:false, providers:1}});
    }
    if (String(url).includes('/models/probe')) {
      const model = JSON.parse(options.body || '{}').model;
      window.uiTest.probes.push(model);
      if (model === 'model-c') return json({model, ok:false, reason:'upstream', status:404, latency_ms:85});
      health[model] = {ok:true, at:Math.floor(Date.now()/1000), latency_ms:95};
      return json({model, ok:true, latency_ms:95});
    }
    if (String(url).includes('/pool/keys/')) {
      const identity = String(url).split('/').pop();
      if (options.method === 'DELETE') {
        const index = pool.keys.findIndex(k=>k.id===identity);
        if (index > -1) pool.keys.splice(index, 1);
        if (pool.active_id === identity) pool.active_id = pool.keys[0]?.id || null;
        pool.next_id = pool.keys[1]?.id || null;
        return json(status());
      }
      const body = JSON.parse(options.body || '{}');
      const item = pool.keys.find(k=>String(url).endsWith(k.id));
      if (item) {Object.assign(item,body); item.state=item.enabled?'standby':'disabled';}
      return json(status());
    }
    if (!String(url).includes('/v1/chat/completions')) return original(url,options);
    const body = JSON.parse(options.body); window.uiTest.calls.push(body);
    const content = body.messages.at(-1).content;
    const text = typeof content==='string'?content:content.find(p=>p.type==='text').text;
    const encoder = new TextEncoder();
    const sse = value => 'data: '+JSON.stringify(value)+'\n\n';
    if (text==='stop-test') return new Response(new ReadableStream({start(controller) {
      controller.enqueue(encoder.encode(sse({choices:[{delta:{content:'جزء محفوظ قبل الإيقاف'}}]})));
      options.signal.addEventListener('abort',()=>controller.error(new DOMException('Aborted','AbortError')),{once:true});
    }}), {headers:{'Content-Type':'text/event-stream'}});
    if (text==='partial-error') return new Response(sse({choices:[{delta:{content:'جواب جزئي محفوظ'}}]})+
      sse({error:{message:'اختبار انقطاع البث'}}), {headers:{'Content-Type':'text/event-stream'}});
    if (text==='billing-test') return new Response(sse({error:{code:'billing',status:402,message:'no credit'}})+
      'data: [DONE]\n\n', {headers:{'Content-Type':'text/event-stream'}});
    if (text==='table-test') return new Response(sse({choices:[{delta:{content:'| الاسم | القيمة |\n| --- | --- |\n| ألف | 1 |\n\n|---|'}}]})+
      sse({choices:[],usage:{total_tokens:5}})+'data: [DONE]\n\n', {headers:{'Content-Type':'text/event-stream'}});
    if (text==='context-test') return new Response(sse({_gateway:{key_id:'ui-a',provider:'groq',label:'اختبار A',
      model:body.model,switched:false,context:{limit:32768,trimmed:3,truncated:false}}} )+
      sse({model:body.model,choices:[{delta:{content:'جواب مع سياق مختصر'}}]})+
      sse({choices:[],usage:{total_tokens:9}})+'data: [DONE]\n\n', {headers:{'Content-Type':'text/event-stream'}});
    if (text==='fallback-test') return new Response(sse({_gateway:{key_id:'ui-b',provider:'groq',label:'اختبار B',
      model:'model-b',switched:true,pool}})+sse({model:'model-b',choices:[{delta:{content:'جواب من نموذج بديل'}}]})+
      sse({model:'model-b',choices:[{delta:{content:''},finish_reason:'stop'}],usage:{total_tokens:7}})+
      'data: [DONE]\n\n', {headers:{'Content-Type':'text/event-stream'}});
    pool.keys[0].state='budget'; pool.keys[0].tokens=900; pool.keys[0].token_percent=90;
    pool.keys[1].state='active'; pool.keys[1].tokens=55; pool.keys[1].token_percent=5.5;
    pool.active_id='ui-b'; pool.next_id=null; pool.switch_count++;
    const answer = text==='code-test'?'```html\n<div id="proof">Preview OK</div>\n```':'إجابة اختبار واضحة';
    return new Response(sse({_gateway:{key_id:'ui-b',provider:'groq',label:'اختبار B',model:body.model,
      switched:true,pool}})+sse({model:body.model,choices:[{delta:{content:answer}}]})+
      sse({choices:[],usage:{total_tokens:55}})+'data: [DONE]\n\n', {headers:{'Content-Type':'text/event-stream'}});
  };
})();
"""


PROFILE_SCRIPT = r"""
(() => {
  if (localStorage.getItem('proxypal.onboarded.v1') === '1') return;
  localStorage.setItem('proxypal.onboarded.v1', '1');
  let prefs = {};
  try { prefs = JSON.parse(localStorage.getItem('proxypal.preferences.v1')) || {} } catch {}
  prefs.userName = prefs.userName || 'سارة';
  prefs.avatar = prefs.avatar || 'nova';
  localStorage.setItem('proxypal.preferences.v1', JSON.stringify(prefs));
})();
"""


def choose_model(page, model):
    page.locator('.model-trigger').click()
    page.locator('.model-option', has_text=model).first.click()
    expect(page.locator('.model-trigger-label')).to_have_text(model)


def mocked(page):
    page.add_init_script(MOCK_SCRIPT)
    page.add_init_script(PROFILE_SCRIPT)
    page.goto(URL)
    expect(page.locator('.model-trigger-label')).to_have_text('model-a')
    expect(page.locator('.model-trigger .model-dot.ready')).to_be_visible()


def send(page, text):
    page.get_by_role('textbox', name='اكتب رسالتك', exact=True).fill(text)
    page.get_by_role('button', name='إرسال الرسالة', exact=True).click()
    expect(page.get_by_role('button', name='إرسال الرسالة', exact=True)).to_be_visible(timeout=100000)


def contrast_failures(page):
    return page.evaluate(r"""() => {
      const rgb = s=>s.match(/[\d.]+/g).slice(0,3).map(Number);
      const luminance = c=>c.map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4)
        .reduce((n,v,i)=>n+v*[.2126,.7152,.0722][i],0);
      const result=[];
      for (const el of document.querySelectorAll('body *')) {
        const css=getComputedStyle(el),rect=el.getBoundingClientRect();
        if (!rect.width || !rect.height || css.visibility==='hidden' || css.display==='none' || el.closest('[inert]') || el.closest('button:disabled') || el.closest('select') || rect.bottom<0 || rect.top>innerHeight) continue;
        const text=[...el.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim();
        if (!text) continue;
        let parent=el,bg;
        while (parent) { const c=getComputedStyle(parent).backgroundColor; if (c!=='rgba(0, 0, 0, 0)' && c!=='transparent') {bg=c;break;} parent=parent.parentElement; }
        if (!bg) continue;
        const a=luminance(rgb(css.color)),b=luminance(rgb(bg));
        const ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
        const large=parseFloat(css.fontSize)>=24 || (parseFloat(css.fontSize)>=18.66 && parseFloat(css.fontWeight)>=700);
        if (ratio<(large?3:4.5)-.01) result.push({text:text.slice(0,40),ratio,fg:css.color,bg});
      }
      return result;
    }""")


def test_real_arabic_chat_history_and_both_themes(page):
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.add_init_script(PROFILE_SCRIPT)
    page.goto(live_url())
    expect(page.locator('.model-trigger')).to_be_enabled(timeout=15000)
    page.locator('.model-trigger').click()
    options = page.locator('.model-option')
    available = [options.nth(index).locator('.model-option-main bdi').inner_text() for index in range(options.count())]
    assert available
    target = 'allam-2-7b' if 'allam-2-7b' in available else available[0]
    page.locator('.model-option', has_text=target).first.click()
    expect(page.locator('.model-trigger-label')).to_have_text(target)
    send(page, 'احفظ الرقم 27. أجب بكلمة واحدة: تم')
    send(page, 'ما الرقم الذي طلبت منك حفظه؟ أجب بالرقم فقط.')
    expect(page.locator('.assistant-message').last.locator('.message-content')).to_contain_text('27', timeout=100000)
    assert page.locator('.message-error').count() == 0
    assert page.get_by_role('button', name='تفعيل القراءة الصوتية يدويًا').get_attribute('aria-pressed') == 'false'
    assert not contrast_failures(page)
    page.screenshot(path=str(ROOT / 'logs' / 'proxypal-light.png'), full_page=True)
    page.get_by_role('button', name='المظهر الداكن', exact=True).click()
    assert not contrast_failures(page)
    page.screenshot(path=str(ROOT / 'logs' / 'proxypal-dark.png'), full_page=True)
    page.reload()
    expect(page.locator('.assistant-message').last.locator('.message-content')).to_contain_text('27')
    expect(page.locator('.model-trigger-label')).to_have_text(target)
    assert not errors


def test_pool_tokens_mascot_manual_audio_and_selection(page):
    mocked(page)
    bar = page.get_by_role('progressbar', name='استهلاك الرموز للمفتاح النشط')
    expect(bar).to_have_attribute('aria-valuenow', '89')
    expect(page.get_by_role('status', name='حالة الرفيق: يستعد للتبديل')).to_be_visible()
    assert page.locator('.companion-switched').count() == 0
    assert page.locator('.companion-control .mascot-svg.mood-preparing').count() == 1
    page.locator('.topbar-actions').get_by_role('button', name='إخفاء الرفيق', exact=True).click()
    assert page.locator('.companion-control').count() == 0
    page.get_by_role('button', name='إظهار الرفيق', exact=True).click()
    choose_model(page, 'model-b')
    send(page, 'اختبار واجهة')
    expect(page.locator('.pool-trigger .key-name')).to_have_text('اختبار B')
    expect(bar).to_have_attribute('aria-valuenow', '6')
    expect(page.get_by_role('status', name='حالة الرفيق: تم التبديل')).to_be_visible()
    expect(page.locator('.companion-control .mascot-svg.mood-switched')).to_be_visible()
    expect(page.locator('.model-trigger-label')).to_have_text('model-b')
    expect(page.locator('.connection-label .connection-dot.connected')).to_be_visible()
    assert page.evaluate('window.uiTest.speech.length') == 0
    page.get_by_role('button', name='تفعيل القراءة الصوتية يدويًا').click()
    page.locator('.assistant-message').get_by_role('button', name='قراءة', exact=True).click()
    assert page.evaluate('window.uiTest.speech[0].lang') == 'ar-SA'
    page.get_by_role('button', name='تعطيل الصوت', exact=True).click()
    expect(page.locator('.assistant-message').get_by_role('button', name='قراءة', exact=True)).to_be_disabled()
    assert page.evaluate('window.uiTest.cancelled') > 0
    assert not contrast_failures(page)


def test_substitute_model_and_key_switch_badges(page):
    mocked(page)
    send(page, 'fallback-test')
    tag = page.locator('.substituted-tag')
    expect(tag).to_be_visible()
    title = tag.get_attribute('title')
    assert 'model-a' in title and 'model-b' in title
    expect(page.locator('.message-model')).to_have_text('model-b')
    assert 'تم التبديل' in page.locator('.gateway-label').get_attribute('title')
    assert not contrast_failures(page)


def test_partial_errors_and_explicit_stop_keep_text_without_retry(page):
    mocked(page)
    send(page, 'partial-error')
    expect(page.locator('.message-error')).to_contain_text('اختبار انقطاع البث')
    expect(page.locator('.assistant-message .message-content')).to_contain_text('جواب جزئي محفوظ')
    assert page.evaluate('window.uiTest.calls.length') == 1
    page.get_by_role('textbox', name='اكتب رسالتك', exact=True).fill('stop-test')
    page.get_by_role('button', name='إرسال الرسالة', exact=True).click()
    expect(page.locator('.assistant-message').last).to_contain_text('جزء محفوظ قبل الإيقاف')
    page.get_by_role('button', name='إيقاف توليد الرد', exact=True).click()
    expect(page.locator('.message-error').last).to_contain_text('الاحتفاظ')
    expect(page.get_by_role('button', name='إرسال الرسالة', exact=True)).to_be_visible()
    assert page.evaluate('window.uiTest.calls.length') == 2
    expect(page.locator('.assistant-message').last).to_contain_text('جزء محفوظ قبل الإيقاف')


def test_code_preview_search_edit_and_attachments(page, tmp_path):
    mocked(page)
    send(page, 'رسالة أولى')
    send(page, 'code-test')
    page.get_by_role('textbox', name='بحث في الرسائل').fill('code-test')
    page.locator('.user-message').get_by_role('button', name='تعديل', exact=True).click()
    expect(page.get_by_role('textbox', name='تعديل الرسالة')).to_have_value('code-test')
    page.get_by_role('button', name='إلغاء', exact=True).click()
    page.get_by_role('textbox', name='بحث في الرسائل').fill('')
    page.locator('.code-toolbar').get_by_role('button', name='معاينة', exact=True).click()
    expect(page.frame_locator('iframe[title="معاينة الكود في إطار معزول"]').locator('#proof')).to_have_text('Preview OK')
    assert page.locator('iframe').get_attribute('sandbox') == 'allow-scripts'
    page.get_by_role('button', name='إغلاق النافذة', exact=True).click()
    text = 'FULL-CONTEXT-END-' + 'x' * 6000
    attachment = tmp_path / 'context.txt'
    attachment.write_text(text)
    page.locator('input[type=file]').set_input_files(attachment)
    expect(page.locator('.pending-attachments')).to_contain_text('context.txt')
    send(page, 'اقرأ المرفق')
    send(page, 'احتفظ بسياق المرفق')
    calls = page.evaluate('window.uiTest.calls')
    assert text in calls[-1]['messages'][-3]['content']


def test_mobile_themes_settings_and_hud(browser):
    context = browser.new_context(viewport={'width': 390, 'height': 844})
    page = context.new_page()
    mocked(page)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.get_by_role('button', name='إظهار القائمة', exact=True).click()
    assert page.evaluate("() => { const sidebar = document.querySelector('.sidebar'); const r = sidebar.getBoundingClientRect(); const hit = document.elementFromPoint(r.left + r.width / 2, r.top + 40); return sidebar.contains(hit) }")
    page.get_by_role('button', name='عرض تفاصيل مجموعة المفاتيح', exact=True).click()
    expect(page.locator('.pool-hud')).to_be_visible()
    assert not contrast_failures(page)
    page.get_by_role('button', name='إخفاء تفاصيل المفاتيح', exact=True).click()
    page.locator('.sidebar').get_by_role('button', name='إخفاء القائمة', exact=True).click()
    page.get_by_role('button', name='المظهر الداكن', exact=True).click()
    assert not contrast_failures(page)
    page.screenshot(path=str(ROOT / 'logs' / 'proxypal-mobile.png'), full_page=True)
    page.get_by_role('button', name='الإعدادات', exact=True).click()
    expect(page.get_by_role('dialog')).to_be_visible()
    assert not contrast_failures(page)
    page.get_by_role('button', name='API Pool 3', exact=True).click()
    page.locator('.existing-key').first.get_by_role('button', name='تعطيل المفتاح', exact=True).click()
    expect(page.locator('.existing-key').first).to_contain_text('معطّل')
    page.get_by_role('button', name='إغلاق النافذة', exact=True).click()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    context.close()


def test_model_health_hides_disabled_and_probes_in_background(page):
    mocked(page)
    page.locator('.model-trigger').click()
    expect(page.locator('.model-option', has_text='ghost-model')).to_have_count(0)
    expect(page.locator('.model-option', has_text='model-c').locator('.model-dot.unknown')).to_be_visible()
    page.locator('.model-option', has_text='model-b').first.click()
    page.wait_for_function("() => window.uiTest.probes.includes('model-b')")
    expect(page.locator('.model-trigger .model-dot.ready')).to_be_visible()
    page.locator('.model-trigger').click()
    expect(page.locator('.model-option', has_text='model-b').locator('.model-dot.ready')).to_be_visible()
    page.locator('.model-option', has_text='model-c').first.click()
    expect(page.locator('.model-trigger .model-dot.limited')).to_be_visible()
    expect(page.locator('.toast-error')).to_contain_text('فشل اختبار النموذج المحدد')


def test_delete_old_conversations_from_sidebar(page):
    mocked(page)
    send(page, 'محادثة أولى')
    page.locator('.new-chat').click()
    expect(page.locator('.conversation-row')).to_have_count(2)
    first = page.locator('.conversation-row', has_text='محادثة أولى')
    first.hover()
    page.once('dialog', lambda dialog: dialog.accept())
    first.get_by_role('button', name='حذف «محادثة أولى»', exact=True).click()
    expect(page.locator('.conversation-row')).to_have_count(1)
    expect(page.locator('.toast')).to_contain_text('حُذفت المحادثة')
    last = page.locator('.conversation-row').first
    last.hover()
    page.once('dialog', lambda dialog: dialog.accept())
    last.get_by_role('button', name='حذف «محادثة جديدة»', exact=True).click()
    expect(page.locator('.conversation-row')).to_have_count(1)
    expect(page.locator('.conversation-row')).to_contain_text('محادثة جديدة')


def test_markdown_tables_do_not_leak_separator_rows(page):
    mocked(page)
    send(page, 'table-test')
    content = page.locator('.assistant-message .message-content').last
    table = content.locator('table')
    expect(table).to_be_visible()
    expect(table.locator('th')).to_have_count(2)
    expect(table).to_contain_text('ألف')
    assert '|---|' not in content.inner_text()
    assert '| --- |' not in content.inner_text()


def test_compact_settings_sound_and_folder_context(page):
    mocked(page)
    expect(page.locator('.companion-control .mascot-svg')).to_be_visible()
    page.locator('.profile').get_by_role('button', name='الإعدادات', exact=True).click()
    dialog = page.get_by_role('dialog')
    fold = dialog.locator('.settings-fold')
    assert page.evaluate("() => document.querySelector('.settings-fold').open") is False
    fold.locator('summary').click()
    expect(dialog.locator('.fold-root')).to_contain_text('/workspace')
    expect(dialog.locator('.fold-body input')).to_have_value('/workspace')
    dialog.get_by_role('button', name='تحميل السياق', exact=True).click()
    expect(page.locator('.toast')).to_contain_text('تم تحميل')
    sound = dialog.locator('.setting-toggle', has_text='المؤثرات الصوتية')
    expect(sound).to_contain_text('مفعّلة')
    sound.get_by_role('button').click()
    expect(sound.get_by_role('button')).to_have_attribute('aria-pressed', 'false')
    page.wait_for_function("() => JSON.parse(localStorage.getItem('proxypal.preferences.v1')).sound === false")
    assert not contrast_failures(page)


def test_delete_api_key_from_settings(page):
    mocked(page)
    page.locator('.profile').get_by_role('button', name='الإعدادات', exact=True).click()
    dialog = page.get_by_role('dialog')
    dialog.get_by_role('button', name='API Pool 3', exact=True).click()
    expect(dialog.locator('.existing-key')).to_have_count(3)
    first = dialog.locator('.existing-key').first
    expect(first).to_contain_text('اختبار A')
    page.once('dialog', lambda confirm: confirm.accept())
    first.get_by_role('button', name='حذف المفتاح', exact=True).click()
    expect(dialog.locator('.existing-key')).to_have_count(2)
    expect(page.locator('.toast')).to_contain_text('حُذف المفتاح')
    expect(dialog.locator('.existing-key').first).to_contain_text('اختبار B')
    page.get_by_role('button', name='إغلاق النافذة', exact=True).click()
    expect(page.locator('.pool-trigger .key-name')).to_have_text('اختبار B')


def test_provider_rows_can_be_deleted_and_models_edited(page):
    mocked(page)
    page.locator('.profile').get_by_role('button', name='الإعدادات', exact=True).click()
    dialog = page.get_by_role('dialog')
    dialog.get_by_role('button', name='API Pool 3', exact=True).click()
    rows = dialog.locator('.provider-row')
    expect(rows).to_have_count(2)
    groq = rows.filter(has_text='groq').first
    expect(groq.locator('.model-chip')).to_have_count(3)
    groq.locator('.model-chip').first.get_by_role('button').click()
    expect(groq.locator('.model-chip')).to_have_count(2)
    expect(page.locator('.toast')).to_contain_text('حُذف النموذج')
    groq.locator('.model-add input').fill('model-d')
    groq.locator('.model-add button').click()
    expect(groq.locator('.model-chip')).to_have_count(3)
    expect(groq.locator('.model-chip').last).to_contain_text('model-d')
    page.once('dialog', lambda confirm: confirm.accept())
    groq.get_by_role('button', name='حذف المزود', exact=True).click()
    expect(dialog.locator('.provider-row')).to_have_count(1)
    expect(page.locator('.toast')).to_contain_text('حُذف المزود')
    assert not contrast_failures(page)


def test_locales_themes_fonts_and_voice_route(page):
    mocked(page)
    expect(page.locator('.connection-label .connection-dot.connected')).to_be_visible()
    expect(page.locator('.model-trigger .model-dot.ready')).to_be_visible()
    send(page, 'اختبار القراءة')
    page.locator('.profile').get_by_role('button', name='الإعدادات', exact=True).click()
    dialog = page.get_by_role('dialog')
    expect(dialog).to_be_visible()
    assert dialog.locator('.segmented button').count() == 3
    assert dialog.locator('.theme-choice').count() == 5
    assert dialog.locator('.font-choice').count() == 5

    dialog.get_by_role('button', name='English', exact=True).click()
    assert page.evaluate('document.documentElement.dir') == 'ltr'
    assert page.evaluate('document.documentElement.lang') == 'en'
    expect(page.get_by_role('button', name='Enable manual read-aloud')).to_have_attribute('aria-pressed', 'false')
    assert not contrast_failures(page)

    dialog.get_by_role('button', name='Français', exact=True).click()
    assert page.evaluate('document.documentElement.dir') == 'ltr'
    assert page.evaluate('document.documentElement.lang') == 'fr'
    assert not contrast_failures(page)

    dialog.get_by_role('button', name='العربية', exact=True).click()
    assert page.evaluate('document.documentElement.dir') == 'rtl'

    for index, theme in enumerate(['light', 'dark', 'navy', 'wheat', 'black']):
        dialog.locator('.theme-choice').nth(index).click()
        assert page.evaluate('document.documentElement.dataset.theme') == theme
        assert not contrast_failures(page)
    dialog.locator('.theme-choice').nth(0).click()

    for index, font in enumerate(['plex', 'tajawal', 'cairo', 'naskh', 'kufi']):
        dialog.locator('.font-choice').nth(index).click()
        assert page.evaluate('document.documentElement.dataset.font') == font
        assert not contrast_failures(page)

    dialog.get_by_label('لغة القراءة').select_option('en')
    dialog.get_by_role('button', name='إغلاق النافذة', exact=True).click()
    page.get_by_role('button', name='تفعيل القراءة الصوتية يدويًا').click()
    page.locator('.assistant-message').last.get_by_role('button', name='قراءة', exact=True).click()
    page.wait_for_function("() => window.uiTest.speech[0]?.lang === 'en-US'")
    page.screenshot(path=str(ROOT / 'logs' / 'proxypal-themes.png'), full_page=True)


def test_routing_custom_provider_key_validation_and_context_chip(page):
    mocked(page)
    page.locator('.profile').get_by_role('button', name='الإعدادات', exact=True).click()
    dialog = page.get_by_role('dialog')
    dialog.get_by_role('button', name='API Pool 3', exact=True).click()
    expect(dialog.locator('.strategy-choice')).to_have_count(3)
    dialog.locator('.strategy-choice', has_text='توزيع بالتناوب').click()
    expect(page.locator('.toast')).to_contain_text('تم تحديث استراتيجية التبديل')
    expect(dialog.locator('.strategy-choice.selected')).to_contain_text('توزيع بالتناوب')

    dialog.get_by_label('اسم المزود').fill('localai')
    dialog.get_by_label('العنوان الأساسي').fill('https://local.test/v1')
    dialog.get_by_label('النماذج (مفصولة بفواصل)').fill('custom-one, custom-two')
    dialog.get_by_role('button', name='إضافة المزود', exact=True).click()
    expect(page.locator('.toast')).to_contain_text('أُضيف المزود')
    localai = dialog.locator('.provider-row').filter(has_text='localai')
    expect(localai).to_contain_text('مخصص')
    expect(localai.locator('.model-chip')).to_have_count(2)
    expect(localai).to_contain_text('https://local.test/v1')
    expect(dialog.locator('.provider-chip', has_text='localai')).to_have_count(1)

    dialog.locator('textarea.secret-input').fill('bad-key-1')
    dialog.get_by_role('button', name='إضافة إلى المجموعة الحالية', exact=True).click()
    expect(page.locator('.toast-error')).to_contain_text('لم يُضف أي مفتاح')
    expect(dialog.locator('.existing-key')).to_have_count(3)
    dialog.get_by_role('button', name='إغلاق النافذة', exact=True).click()

    send(page, 'context-test')
    chip = page.locator('.assistant-message').last.locator('.context-tag')
    expect(chip).to_contain_text('سياق مختصر')
    expect(chip).to_have_attribute('title', 'حُذفت 3 من الرسائل القديمة لتلائم حد سياق النموذج (32,768 رمز). المحادثة كاملة محفوظة هنا.')
    page.screenshot(path=str(ROOT / 'logs' / 'proxypal-routing-context.png'), full_page=True)


def test_gateway_token_from_url_is_sent_and_removed(page):
    page.add_init_script(MOCK_SCRIPT)
    page.add_init_script(PROFILE_SCRIPT)
    page.goto(URL + '/?token=secret-ui-token')
    expect(page.locator('.model-trigger-label')).to_have_text('model-a')
    assert page.evaluate("localStorage.getItem('proxypal.gatewayToken')") == 'secret-ui-token'
    assert page.evaluate('location.search') == ''
    assert page.evaluate("window.uiTest.auth.filter(Boolean).at(-1)") == 'Bearer secret-ui-token'


def test_onboarding_collects_first_name_avatar_and_greets(page):
    page.add_init_script(MOCK_SCRIPT)
    page.goto(URL)
    card = page.locator('.onboarding-card')
    expect(card).to_be_visible(timeout=10000)
    expect(page.locator('.splash')).to_have_count(0)
    page.get_by_label('الاسم الأول', exact=True).fill('هيرغافي')
    card.get_by_role('button', name='لونا', exact=True).click()
    page.get_by_role('button', name='ابدأ المحادثة', exact=True).click()
    expect(card).to_have_count(0)
    expect(page.locator('.assistant-message').last.locator('.message-content')).to_contain_text('مرحباً "هيرغافي" ^^')
    expect(page.locator('.profile .avatar img')).to_have_attribute('src', './avatars/luna.svg')
    page.wait_for_function("() => JSON.parse(localStorage.getItem('proxypal.preferences.v1') || '{}').avatar === 'luna'")
    assert page.evaluate("localStorage.getItem('proxypal.onboarded.v1')") == '1'
    page.screenshot(path=str(ROOT / 'logs' / 'proxypal-onboarding.png'), full_page=True)


def test_provider_catalog_shows_logos_and_expands(page):
    mocked(page)
    page.locator('.profile').get_by_role('button', name='الإعدادات', exact=True).click()
    dialog = page.get_by_role('dialog')
    dialog.get_by_role('button', name='API Pool 3', exact=True).click()
    chips = dialog.locator('.provider-chip')
    expect(chips).to_have_count(6)
    expect(chips.locator('.provider-mark')).to_have_count(6)
    dialog.get_by_role('button', name='عرض كل المزودات (14)', exact=True).click()
    expect(chips).to_have_count(14)
    expect(dialog.locator('.provider-chip', has_text='Mistral')).to_be_visible()
    expect(dialog.locator('.provider-chip', has_text='Kimi')).to_be_visible()
    chip = dialog.locator('.provider-chip', has_text='Mistral')
    chip.click()
    expect(chip).to_have_attribute('aria-pressed', 'true')


def test_billing_error_is_explained_instead_of_no_key(page):
    mocked(page)
    send(page, 'billing-test')
    message = page.locator('.assistant-message').last
    expect(message).to_contain_text('رصيد الحساب انتهى')
    expect(message).to_contain_text('402')
    expect(message).to_contain_text('غير مكتمل')


def test_update_button_refreshes_models_in_parallel_and_hides_failed(page):
    mocked(page)
    page.locator('.model-trigger').click()
    expect(page.locator('.model-option', has_text='model-new')).to_have_count(0)
    page.get_by_role('button', name='تحديث وفحص النماذج', exact=True).click()
    expect(page.locator('.toast')).to_contain_text('حُدّثت القائمة')
    expect(page.locator('.model-option', has_text='model-new')).to_be_visible()
    # A model the provider rejects outright is removed instead of staying as a trap.
    expect(page.locator('.model-option', has_text='model-b')).to_have_count(0)
    assert page.evaluate('window.uiTest.refreshes') == 1
    expect(page.locator('.model-trigger .model-dot.ready')).to_be_visible()


def test_composer_keeps_focus_and_draft_during_and_after_reply(page):
    mocked(page)
    box = page.get_by_role('textbox', name='اكتب رسالتك', exact=True)
    box.fill('stop-test')
    page.get_by_role('button', name='إرسال الرسالة', exact=True).click()
    expect(page.locator('.assistant-message').last).to_contain_text('جزء محفوظ قبل الإيقاف')
    expect(box).to_be_enabled()
    page.wait_for_function("() => document.activeElement?.id === 'composer'")
    box.type('مسودة أثناء الرد')
    assert box.input_value() == 'مسودة أثناء الرد'
    page.get_by_role('button', name='إيقاف توليد الرد', exact=True).click()
    expect(page.get_by_role('button', name='إرسال الرسالة', exact=True)).to_be_visible()
    expect(box).to_have_value('مسودة أثناء الرد')
    page.wait_for_function("() => document.activeElement?.id === 'composer'")
    box.fill('')
    send(page, 'رد عادي')
    expect(page.locator('.assistant-message').last).to_contain_text('إجابة اختبار واضحة')
    page.wait_for_function("() => document.activeElement?.id === 'composer'")


def test_rename_pin_and_persist_conversations(page):
    mocked(page)
    row = page.locator('.conversation-row').first
    row.hover()
    row.get_by_role('button', name='إعادة تسمية «محادثة جديدة»', exact=True).click()
    field = page.get_by_label('اسم المحادثة', exact=True)
    field.fill('خطة التصميم')
    page.get_by_role('button', name='حفظ الاسم', exact=True).click()
    expect(page.locator('.toast')).to_contain_text('تم تحديث اسم المحادثة')
    expect(page.locator('.conversation-row').first).to_contain_text('خطة التصميم')

    row = page.locator('.conversation-row').first
    row.hover()
    row.get_by_role('button', name='تثبيت المحادثة', exact=True).click()
    expect(page.locator('.toast')).to_contain_text('ثُبّتت المحادثة في الأعلى')
    expect(row).to_have_class('conversation-row selected pinned')
    page.locator('.new-chat').click()
    expect(page.locator('.conversation-row').first).to_contain_text('خطة التصميم')

    page.reload()
    expect(page.locator('.conversation-row').first).to_contain_text('خطة التصميم')
    expect(page.locator('.conversation-row').first).to_have_class('conversation-row pinned')
    expect(page.locator('.conversation-row').nth(1)).to_contain_text('محادثة جديدة')
    expect(page.locator('.chat-breadcrumb')).to_contain_text('محادثة جديدة')
    page.screenshot(path=str(ROOT / 'logs' / 'proxypal-conversation-management.png'), full_page=True)
