import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import './fonts.css'
import './index.css'
import { darkThemes, fonts, localeInfo, locales, themes, translator } from './i18n'

const GW = (import.meta.env.VITE_GATEWAY_URL || 'http://127.0.0.1:8790').replace(/\/$/, '')
const GATEWAY_VERSION = 6 // Keep in sync with gateway.py and run.bat.
const TOKEN_KEY = 'proxypal.gatewayToken'
const initialUrl = new URL(window.location.href)
if (initialUrl.searchParams.get('token')) {
  localStorage.setItem(TOKEN_KEY, initialUrl.searchParams.get('token').trim())
  initialUrl.searchParams.delete('token')
  window.history.replaceState({}, '', initialUrl)
}
function gatewayToken() { return (localStorage.getItem(TOKEN_KEY) || import.meta.env.VITE_GATEWAY_TOKEN || '').trim() }
function authHeaders(extra = {}) { const token = gatewayToken(); return token ? { ...extra, Authorization: `Bearer ${token}` } : extra }
const STORE = 'proxypal.conversations.v1'
const ACTIVE = 'proxypal.activeConversation.v1'
const PREFS = 'proxypal.preferences.v1'
const ONBOARDED = 'proxypal.onboarded.v1'
const AVATARS = ['nova', 'sunny', 'luna']
const AVATAR_SRC = { nova: './avatars/nova.svg', sunny: './avatars/sunny.svg', luna: './avatars/luna.svg' }
const PROVIDER_CATALOG = [
  { id: 'groq', name: 'Groq', tone: '#f55036', glyph: 'bolt' },
  { id: 'openrouter', name: 'OpenRouter', tone: '#6d5dfc', glyph: 'router' },
  { id: 'gemini', name: 'Gemini', tone: '#4285f4', glyph: 'spark' },
  { id: 'openai', name: 'OpenAI', tone: '#10a37f', glyph: 'orbit' },
  { id: 'anthropic', name: 'Anthropic', tone: '#d97757', glyph: 'asterisk' },
  { id: 'mistral', name: 'Mistral', tone: '#f2542d', glyph: 'bars' },
  { id: 'deepseek', name: 'DeepSeek', tone: '#4d6bfe', glyph: 'wave' },
  { id: 'moonshot', name: 'Kimi', tone: '#26262b', glyph: 'moon' },
  { id: 'llama', name: 'Meta Llama', tone: '#0866ff', glyph: 'infinity' },
  { id: 'github', name: 'GitHub Models', tone: '#24292f', glyph: 'cat' },
  { id: 'xai', name: 'xAI', tone: '#111111', glyph: 'x' },
  { id: 'together', name: 'Together', tone: '#0ea5e9', glyph: 'nodes' },
  { id: 'fireworks', name: 'Fireworks', tone: '#e11d48', glyph: 'burst' },
  { id: 'cerebras', name: 'Cerebras', tone: '#0d9488', glyph: 'chip' },
]
const POPULAR_PROVIDERS = 6
const BRAIN_PATH = 'M24,11c0-1.568-.752-3.04-2-3.979v-.021c0-1.897-1.327-3.489-3.102-3.898-.409-1.774-2.002-3.102-3.898-3.102-1.194,0-2.267,.526-3,1.357-.733-.832-1.806-1.357-3-1.357-1.896,0-3.489,1.327-3.898,3.102-1.774,.409-3.102,2.001-3.102,3.898v.021c-1.248,.939-2,2.41-2,3.979,0,.886,.235,1.737,.686,2.5-.45,.763-.686,1.614-.686,2.5,0,1.686,.858,3.244,2.267,4.166,.719,2.278,2.812,3.834,5.233,3.834,1.858,0,3.504-.926,4.5-2.342,.996,1.415,2.642,2.342,4.5,2.342,2.422,0,4.515-1.556,5.233-3.834,1.408-.922,2.267-2.48,2.267-4.166,0-.886-.235-1.737-.686-2.5,.45-.763,.686-1.614,.686-2.5ZM7.5,22c-1.634,0-3.033-1.115-3.401-2.712-.065-.281-.248-.52-.502-.656-.985-.528-1.597-1.536-1.597-2.631,0-.675,.234-1.322,.679-1.872,.296-.367,.296-.89,0-1.257-.444-.549-.679-1.196-.679-1.872,0-1.07,.591-2.067,1.543-2.603,.37-.208,.568-.627,.494-1.045-.02-.115-.037-.231-.037-.352,0-1.103,.897-2,2-2,.553,0,1-.448,1-1,0-1.103,.897-2,2-2s2,.897,2,2v4h-2.268c-.346-.598-.992-1-1.732-1-1.105,0-2,.895-2,2s.895,2,2,2c.74,0,1.386-.402,1.732-1h2.268v5h-2.268c-.346-.598-.992-1-1.732-1-1.105,0-2,.895-2,2s.895,2,2,2c.74,0,1.386-.402,1.732-1h2.268v1.5c0,1.93-1.57,3.5-3.5,3.5Zm13.821-7.872c.444,.549,.679,1.196,.679,1.872,0,1.096-.611,2.104-1.597,2.631-.254,.136-.437,.375-.502,.656-.368,1.597-1.768,2.712-3.401,2.712-1.93,0-3.5-1.57-3.5-3.5v-4.5h2c1.654,0,3-1.346,3-3v-.268c.598-.346,1-.992,1-1.732,0-1.105-.895-2-2-2s-2,.895-2,2c0,.74,.402,1.386,1,1.732v.268c0,.551-.448,1-1,1h-2V4c0-1.103,.897-2,2-2s2,.897,2,2c0,.552,.447,1,1,1,1.103,0,2,.897,2,2,0,.121-.018,.237-.037,.352-.074,.418,.124,.837,.494,1.045,.952,.535,1.543,1.533,1.543,2.603,0,.675-.234,1.322-.679,1.872-.296,.367-.296,.89,0,1.257Z'
const INACTIVITY_MS = 90000
const MODEL_OK_TTL = 6 * 60 * 60 * 1000
const MODEL_FAIL_TTL = 60 * 60 * 1000
const SPEECH_CODES = { ar: 'ar-SA', en: 'en-US', fr: 'fr-FR' }
const AGENTS = [
  { id: 'general', labelKey: 'agent_general', prompt: '' },
  { id: 'code', labelKey: 'agent_code', prompt: 'You are an expert code specialist.' },
  { id: 'data', labelKey: 'agent_data', prompt: 'You are a data analyst.' },
  { id: 'writer', labelKey: 'agent_writer', prompt: 'You are a creative writer.' },
]
const STATE_LABELS = { active: 'stateActive', standby: 'stateStandby', cooldown: 'stateCooldown', budget: 'stateBudget', disabled: 'stateDisabled', blocked: 'stateBlocked', busy: 'stateBusy' }
function keyStateLabel(item, t) {
  if (item?.state === 'blocked' && item.last_error?.reason === 'billing') return t('stateBilling')
  return t(STATE_LABELS[item?.state] || 'stateActive')
}
const PROMPTS = [
  { icon: 'code', titleKey: 'prompt1Title', textKey: 'prompt1Text', hintKey: 'prompt1Hint' },
  { icon: 'file', titleKey: 'prompt2Title', textKey: 'prompt2Text', hintKey: 'prompt2Hint' },
  { icon: 'pen', titleKey: 'prompt3Title', textKey: 'prompt3Text', hintKey: 'prompt3Hint' },
  { icon: 'spark', titleKey: 'prompt4Title', textKey: 'prompt4Text', hintKey: 'prompt4Hint' },
]
const THEME_PREVIEW = {
  light: { bg: '#f9f9f9', surface: '#ffffff', accent: '#2c2c2c', border: '#dedede' },
  dark: { bg: '#191919', surface: '#202020', accent: '#dedede', border: '#353535' },
  navy: { bg: '#0a1220', surface: '#101b2d', accent: '#d7e6ff', border: '#263a55' },
  wheat: { bg: '#f7f1e5', surface: '#fffaf1', accent: '#43331d', border: '#dbcdb4' },
  black: { bg: '#050505', surface: '#0d0d0d', accent: '#f4f4f4', border: '#242424' },
}

function Icon({ name, size = 18, ...props }) {
  const paths = {
    chat: <><path d="M4 6a3 3 0 0 1 3-3h10a3 3 0 0 1 3 3v7a3 3 0 0 1-3 3H9l-5 4V6Z" /><path d="M8 8h8M8 11.5h5" /></>,
    plus: <path d="M12 5v14M5 12h14" />,
    close: <path d="m6 6 12 12M18 6 6 18" />,
    sidebar: <><rect x="3" y="4" width="18" height="16" rx="3" /><path d="M9 4v16" /><path d="M5.5 8h1M5.5 11h1" /></>,
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></>,
    settings: <><path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1" /><circle cx="15" cy="6" r="2" /><circle cx="9" cy="12" r="2" /><circle cx="17" cy="18" r="2" /></>,
    sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M5 19l1.5-1.5M17.5 6.5 19 5" /></>,
    moon: <path d="M21 13A9 9 0 0 1 11 3a9 9 0 1 0 10 10Z" />,
    send: <><path d="m4 12 16-8-6.5 16-2.5-5.5L4 12Z" /><path d="m11 14.5 9-10.5" /></>,
    chevron: <path d="m6 9 6 6 6-6" />,
    chevronUp: <path d="m6 15 6-6 6 6" />,
    stop: <rect x="6" y="6" width="12" height="12" rx="2" />,
    audio: <><path d="m11 5-5 4H3v6h3l5 4V5Z" /><path d="M15 8a6 6 0 0 1 0 8M18 5a10 10 0 0 1 0 14" /></>,
    muted: <><path d="m11 5-5 4H3v6h3l5 4V5Z" /><path d="m16 9 5 6M21 9l-5 6" /></>,
    mic: <><rect x="9" y="2" width="6" height="13" rx="3" /><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8" /></>,
    attach: <path d="m8 13 7-7a3 3 0 0 1 4 4L9 20a5 5 0 0 1-7-7L13 2m-8 14 10-10" />,
    key: <><circle cx="8" cy="9" r="5" /><path d="m12 13 8 8h2v-4h-3v-3h-3M7 8h.01" /></>,
    layers: <><path d="m12 3 10 5-10 5L2 8l10-5Z" /><path d="m2 12 10 5 10-5M2 16l10 5 10-5" /></>,
    copy: <><rect x="8" y="8" width="12" height="13" rx="2" /><path d="M15 8V3H3v12h5" /></>,
    refresh: <><path d="M20 8a8 8 0 0 0-14-3L3 8m0-5v5h5" /><path d="M4 16a8 8 0 0 0 14 3l3-3m0 5v-5h-5" /></>,
    pen: <><path d="m15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-4-4L5 15v5Z" /><path d="M4 20h16" /></>,
    pin: <><path d="M9 3h6l-1 6 3 3v2H7v-2l3-3-1-6Z" /><path d="M12 14v7" /></>,
    download: <><path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5" /></>,
    code: <path d="m7 6-6 6 6 6M17 6l6 6-6 6M14 3l-4 18" />,
    eye: <><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></>,
    file: <><path d="M14 2H5v20h14V7l-5-5Z" /><path d="M14 2v5h5M8 12h8M8 16h6" /></>,
    spark: <path d="m12 2 2.5 7.5L22 12l-7.5 2.5L12 22l-2.5-7.5L2 12l7.5-2.5L12 2Z" />,
    check: <path d="m5 12 4 4L19 6" />,
    info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 7h.01" /></>,
    focus: <path d="M8 3H3v5M16 3h5v5M3 16v5h5M21 16v5h-5" />,
    robot: <><rect x="4" y="7" width="16" height="13" rx="5" /><path d="M12 7V3M10 3h4M8 12h.01M16 12h.01M9 16h6M1 11v5M23 11v5" /></>,
    cat: <><path d="M4 11V3l6 4h4l6-4v8a8 8 0 0 1-16 0Z" /><path d="M8 12h.01M16 12h.01m-5 3 1 1 1-1M2 14l5 1M17 15l5-1" /></>,
    orb: <><circle cx="12" cy="12" r="9" /><path d="M7 11h.01M17 11h.01M9 15q3 2 6 0M6 6q4-3 7-2" /></>,
    globe: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.5 3 3.8 6 3.8 9S14.5 18 12 21M12 3c-2.5 3-3.8 6-3.8 9S9.5 18 12 21" /></>,
    type: <><path d="M4 6V4h16v2M12 4v16M8 20h8" /></>,
    palette: <><path d="M12 3a9 9 0 1 0 0 18c1.5 0 2.6-1.1 2.6-2.6 0-1.4-1.1-2.5-2.6-2.5h-1a2.8 2.8 0 0 1 0-5.6h3A6 6 0 0 0 20 4.7 9 9 0 0 0 12 3Z" /><circle cx="7.5" cy="10.5" r=".9" /><circle cx="9.5" cy="7" r=".9" /><circle cx="14" cy="6.2" r=".9" /></>,
    wave: <path d="M4 10v4M8 6v12M12 3v18M16 7v10M20 10v4" />,
    plug: <><path d="M9 2v6M15 2v6M6 8h12v3a6 6 0 0 1-6 6 6 6 0 0 1-6-6V8Z" /><path d="M12 17v5" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    trash: <><path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14M10 11v6M14 11v6" /></>,
  }
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name] || paths.chat}</svg>
}

function IconButton({ icon, label, className = '', ...props }) {
  return <button type="button" className={`icon-button ${className}`} aria-label={label} title={label} {...props}><Icon name={icon} /></button>
}

function Logo({ size = 24, className = '' }) {
  return <svg className={`logo-mark ${className}`} width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d={BRAIN_PATH} /></svg>
}

function Avatar({ id, name, className = '' }) {
  const src = AVATAR_SRC[id]
  return <span className={`avatar ${src ? 'has-image' : ''} ${className}`}>{src ? <img src={src} alt="" /> : (String(name || '').trim().charAt(0) || 'P')}</span>
}

const PROVIDER_GLYPHS = {
  bolt: <path d="M13 2 4 14h6l-1 8 9-12h-6l1-8Z" fill="#fff" stroke="none" />,
  router: <><circle cx="12" cy="12" r="3" /><path d="M12 3v6M12 15v6M3 12h6M15 12h6" /></>,
  spark: <path d="m12 3 2.4 6.6L21 12l-6.6 2.4L12 21l-2.4-6.6L3 12l6.6-2.4L12 3Z" fill="#fff" stroke="none" />,
  orbit: <><circle cx="12" cy="12" r="4" /><ellipse cx="12" cy="12" rx="9" ry="4.5" transform="rotate(-25 12 12)" /></>,
  asterisk: <path d="M12 3v18M4.2 7.5l15.6 9M19.8 7.5l-15.6 9" />,
  bars: <path d="M5 18 9 6M10 18l4-12M15 18l4-12" strokeWidth="2.4" />,
  wave: <path d="M3 14c3-6 6 6 9 0s6-6 9 0" />,
  moon: <path d="M20 14A8 8 0 0 1 10 4a8 8 0 1 0 10 10Z" fill="#fff" stroke="none" />,
  infinity: <path d="M12 12c-2-3-3.5-4.5-5.5-4.5a4.5 4.5 0 1 0 0 9C8.5 16.5 10 15 12 12Zm0 0c2 3 3.5 4.5 5.5 4.5a4.5 4.5 0 1 0 0-9C15.5 7.5 14 9 12 12Z" />,
  cat: <><path d="M5 10V4l5 3h4l5-3v6a7 7 0 0 1-14 0Z" /><path d="M9 12h.01M15 12h.01M10 15h4" /></>,
  x: <path d="M5 5l14 14M19 5 5 19" />,
  nodes: <><circle cx="6" cy="7" r="2.5" /><circle cx="18" cy="7" r="2.5" /><circle cx="12" cy="18" r="2.5" /><path d="m8 9 2.8 6.5M16 9l-2.8 6.5M8.5 7h7" /></>,
  burst: <path d="m12 2 2 7 6-3-3 6 7 2-7 2 3 6-6-3-2 7-2-7-6 3 3-6-7-2 7-2-3-6 6 3 2-7Z" fill="#fff" stroke="none" />,
  chip: <><rect x="7" y="7" width="10" height="10" rx="2" /><path d="M9 3v4M15 3v4M9 17v4M15 17v4M3 9h4M3 15h4M17 9h4M17 15h4" /></>,
}
function ProviderMark({ id, size = 22 }) {
  const provider = PROVIDER_CATALOG.find(item => item.id === id)
  if (!provider) return <span className="provider-mark provider-mark-custom" style={{ width: size, height: size }}>{String(id || '?').charAt(0).toUpperCase()}</span>
  return <span className="provider-mark" style={{ width: size, height: size, background: provider.tone }}>
    <svg viewBox="0 0 24 24" width={size * 0.62} height={size * 0.62} fill="none" stroke="#fff" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{PROVIDER_GLYPHS[provider.glyph]}</svg>
  </span>
}

function Mascot({ shape = 'orb', mood = 'idle', size = 48, className = '' }) {
  const sleepy = mood === 'sleepy'
  const thinking = mood === 'thinking'
  const wide = mood === 'preparing'
  const joyful = mood === 'happy' || mood === 'switched'
  const starry = mood === 'switched'
  const eyeY = thinking ? 27.5 : 30
  const mouth = sleepy ? 'M27 40h10' : joyful ? 'M24 36.5c4 6.5 12 6.5 16 0' : thinking ? 'M28.5 40c2.2 1.4 4.8 1.4 7 0' : wide ? 'M29 37.5a3.2 3.2 0 0 0 6 0' : 'M26 38.5c3 3.2 9 3.2 12 0'
  const orbEyes = starry
    ? <><path d="m24 25 1.6 3.9L30 30l-4.4 1.1L24 35l-1.6-3.9L18 30l4.4-1.1L24 25Z" fill="currentColor" /><path d="m40 25 1.6 3.9L46 30l-4.4 1.1L40 35l-1.6-3.9L34 30l4.4-1.1L40 25Z" fill="currentColor" /></>
    : sleepy
      ? <><path d="M21 31q3 2.2 6 0M37 31q3 2.2 6 0" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" /></>
      : wide
        ? <><circle cx="25" cy="30" r="3.4" fill="currentColor" /><circle cx="39" cy="30" r="3.4" fill="currentColor" /><circle cx="26.1" cy="28.9" r="1" fill="var(--surface)" /><circle cx="40.1" cy="28.9" r="1" fill="var(--surface)" /></>
        : <><ellipse className="mascot-eye" cx="25" cy={eyeY} rx="2.3" ry="3.1" fill="currentColor" /><ellipse className="mascot-eye" cx="39" cy={eyeY} rx="2.3" ry="3.1" fill="currentColor" /></>
  return <svg className={`mascot-svg mood-${mood} ${className}`} width={size} height={size} viewBox="0 0 64 64" fill="none" aria-hidden="true">
    <g className="mascot-float">
      <ellipse cx="32" cy="56" rx="14" ry="2.6" fill="var(--border)" opacity=".7" />
      {shape === 'robot' ? <>
        <path d="M32 12v5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <circle cx="32" cy="10.5" r="2.4" fill="currentColor" />
        <rect x="7" y="27" width="5" height="11" rx="2.5" fill="currentColor" opacity=".45" />
        <rect x="52" y="27" width="5" height="11" rx="2.5" fill="currentColor" opacity=".45" />
        <rect x="13" y="17" width="38" height="33" rx="12" fill="var(--surface-alt)" stroke="currentColor" strokeWidth="2.2" />
        {sleepy ? <><path d="M22 31q3 2 6 0M36 31q3 2 6 0" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" /></>
          : <><rect className="mascot-eye" x="22.5" y={eyeY - 3} width="5" height="6" rx="2.4" fill="currentColor" /><rect className="mascot-eye" x="36.5" y={eyeY - 3} width="5" height="6" rx="2.4" fill="currentColor" /></>}
        <path d={mouth} stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" />
        <circle cx="19" cy="37" r="2" fill="var(--warning)" opacity={joyful ? '.55' : '.2'} />
        <circle cx="45" cy="37" r="2" fill="var(--warning)" opacity={joyful ? '.55' : '.2'} />
      </> : shape === 'cat' ? <>
        <path d="M14 33V14l11 7h14l11-7v19a18 18 0 0 1-36 0Z" fill="var(--surface-alt)" stroke="currentColor" strokeWidth="2.2" strokeLinejoin="round" />
        <path d="M19 18v8l6-4M45 18v8l-6-4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
        {sleepy ? <><path d="M22 31q3 2 6 0M36 31q3 2 6 0" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" /></>
          : starry ? <><path d="m24 25 1.3 3.3 3.4.5-3 2.1.8 4-2.5-2.6-3.8 1 1.8-3.4L19 26l3.9.3L24 25Z" fill="currentColor" /><path d="m40 25 1.3 3.3 3.4.5-3 2.1.8 4-2.5-2.6-3.8 1 1.8-3.4L35 26l3.9.3L40 25Z" fill="currentColor" /></>
            : <><ellipse className="mascot-eye" cx="25" cy={eyeY} rx="2.3" ry="3" fill="currentColor" /><ellipse className="mascot-eye" cx="39" cy={eyeY} rx="2.3" ry="3" fill="currentColor" /></>}
        <path d="m32 35 2 2-2 1.7-2-1.7 2-2Z" fill="currentColor" />
        <path d={mouth} stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
        <path d="M10 33h8M9 37l8-1M46 33h8M55 37l-8-1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" opacity=".65" />
        <circle cx="19" cy="38" r="2.2" fill="var(--warning)" opacity={joyful ? '.5' : '.18'} />
        <circle cx="45" cy="38" r="2.2" fill="var(--warning)" opacity={joyful ? '.5' : '.18'} />
      </> : <>
        <circle cx="32" cy="32" r="21" fill="var(--surface-alt)" stroke="currentColor" strokeWidth="2.2" />
        <path d="M18 22c4-6 10-9 14-9" stroke="currentColor" strokeWidth="1.6" opacity=".4" strokeLinecap="round" />
        {orbEyes}
        <path d={mouth} stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" />
        <circle cx="20.5" cy="36" r="2.4" fill="var(--warning)" opacity={joyful ? '.5' : '.18'} />
        <circle cx="43.5" cy="36" r="2.4" fill="var(--warning)" opacity={joyful ? '.5' : '.18'} />
      </>}
    </g>
  </svg>
}

function readStored(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) || fallback } catch { return fallback }
}
function uid() { return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}` }
function newConversation(t) { return { id: uid(), title: t('newChat'), updatedAt: Date.now(), pinned: false, messages: [] } }
function conversationOrder(list) {
  return [...list].sort((a, b) => (Number(Boolean(b.pinned)) - Number(Boolean(a.pinned))) || b.updatedAt - a.updatedAt)
}
function loadConversations(t) {
  const saved = readStored(STORE, [])
  if (!Array.isArray(saved)) return [newConversation(t)]
  const valid = saved.filter(c => c && typeof c.id === 'string' && Array.isArray(c.messages)).map(c => ({ ...c, pinned: Boolean(c.pinned), title: typeof c.title === 'string' && c.title.trim() ? c.title : t('newChat'), messages: c.messages.map(m => m.streaming ? { ...m, streaming: false, incomplete: true } : m) }))
  return valid.length ? valid : [newConversation(t)]
}
function textOf(message) {
  if (typeof message.content === 'string') return message.content
  return Array.isArray(message.content) ? message.content.filter(p => p.type === 'text').map(p => p.text).join('\n') : ''
}
function percentage(value) { return Math.min(100, Math.max(0, Number(value) || 0)) }
function number(value) { return new Intl.NumberFormat('en-US').format(Number(value) || 0) }
function errorText(error, t) {
  if (typeof error === 'string') return error
  const codes = { no_key: 'errorNoKey', stream_interrupted: 'errorStreamInterrupted', billing: 'errorBilling',
    model_unavailable: 'errorModelUnavailable', timeout: 'errorProviderTimeout', request: 'errorRequest', upstream: 'errorUpstreamFailed' }
  if (error?.code && codes[error.code]) return t(codes[error.code])
  return error?.message || t('errorStatus')
}
function errorReasonLabel(reason, t) {
  const keys = { credentials: 'errorCredentials', rate_limit: 'errorRateLimit', upstream: 'errorUpstream',
    request: 'errorRequest', billing: 'reasonBilling', model_missing: 'reasonModelMissing', timeout: 'reasonTimeout' }
  return t(keys[reason] || 'errorRequest')
}
function download(content, filename, type = 'text/plain;charset=utf-8') {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
function fileData(file, t) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = () => reject(new Error(t('attachmentRead')))
    reader.readAsDataURL(file)
  })
}
function requestContent(message, newText, imagePrompt) {
  const text = newText === undefined ? textOf(message) : newText
  const attachments = message.attachments || []
  if (!attachments.length) return newText === undefined ? message.requestContent || message.content : text
  const combined = [text, ...attachments.filter(a => a.kind === 'text').map(a => `[File: ${a.name}]\n${a.text}`)].filter(Boolean).join('\n\n')
  const images = attachments.filter(a => a.kind === 'image').map(a => ({ type: 'image_url', image_url: { url: a.url } }))
  return images.length ? [{ type: 'text', text: combined || imagePrompt }, ...images] : combined
}

function providerHealth(pool) {
  const map = {}
  for (const key of pool?.keys || []) {
    const rec = map[key.provider] || { total: 0, ready: 0, cooling: 0, off: 0 }
    rec.total++
    if (!key.enabled || ['disabled', 'blocked'].includes(key.state)) rec.off++
    else if (['active', 'standby'].includes(key.state)) rec.ready++
    else rec.cooling++
    map[key.provider] = rec
  }
  return map
}
function modelHealthRecord(modelHealth, model) {
  const record = modelHealth?.[model]
  if (!record || typeof record !== 'object') return null
  const at = Number(record.at) || 0
  const age = Date.now() - (at > 0 && at < 1e12 ? at * 1000 : at)
  return { ...record, age }
}
function modelStatus(id, modelHealth, testingModel) {
  if (testingModel === id) return 'testing'
  const record = modelHealthRecord(modelHealth, id)
  if (record?.ok === true && record.age <= MODEL_OK_TTL) return 'ready'
  if (record?.ok === false && record.age <= MODEL_FAIL_TTL) return 'limited'
  return 'unknown'
}
function modelOptions(providers, health, selected, modelHealth = {}, testingModel = '') {
  const map = new Map()
  for (const provider of Array.isArray(providers) ? providers : []) {
    const state = health[provider.provider]
    if (!state && provider.key_count === 0) continue
    if (state && state.total > 0 && state.ready + state.cooling === 0) continue
    for (const raw of provider.models || []) {
      const id = typeof raw === 'string' ? raw : raw.id || raw.model || raw.name
      if (!id) continue
      const record = map.get(id) || { id, providers: [] }
      if (provider.provider && !record.providers.includes(provider.provider)) record.providers.push(provider.provider)
      map.set(id, record)
    }
  }
  if (selected && !map.has(selected) && !providers?.length) map.set(selected, { id: selected, providers: [] })
  const providerOrder = new Map((Array.isArray(providers) ? providers : []).map((provider, index) => [provider.provider, index]))
  const rank = { ready: 0, unknown: 1, limited: 2 }
  const options = [...map.values()].map(option => ({
    ...option,
    status: modelStatus(option.id, modelHealth, testingModel),
    health: modelHealthRecord(modelHealth, option.id),
  })).sort((a, b) => rank[a.status] - rank[b.status]
    || (providerOrder.get(a.providers[0]) ?? 99) - (providerOrder.get(b.providers[0]) ?? 99)
    || a.id.localeCompare(b.id))
  // Model-level rejections are definitive. Key, billing and network errors are not.
  return options.filter(option => option.id === selected || !modelLevelFailure(option.health))
}
function modelLevelFailure(record) {
  return Boolean(record && record.ok === false && record.age <= MODEL_FAIL_TTL
    && [400, 404, 422].includes(Number(record.status)))
}
function modelStatusTitle(option, t) {
  if (option.status === 'testing') return t('modelTesting')
  if (option.status === 'ready') return option.health?.latency_ms ? t('modelReadyLatency', { ms: Math.round(option.health.latency_ms) }) : t('modelReady')
  if (option.status === 'limited') {
    const reason = { no_key: 'reasonNoKey', upstream: 'reasonUpstream', fallback: 'reasonFallback', stream: 'reasonStream', probe: 'reasonProbe' }[option.health?.reason] || 'reasonUnknown'
    const status = option.health?.status ? ` · ${t('httpStatus', { status: option.health.status })}` : ''
    return `${t('modelLimited')} · ${t(reason)}${status}`
  }
  return t('modelUntested')
}
function speechText(raw) {
  return String(raw)
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, ' ')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/[*_~>|]/g, ' ')
    .replace(/\s{2,}/g, ' ')
    .trim()
}
function speechChunks(raw, max = 220) {
  const sentences = raw.split(/(?<=[.!?؟])\s+|\n+/).filter(Boolean)
  const chunks = []
  let current = ''
  for (const sentence of sentences) {
    const parts = sentence.length > max ? sentence.match(new RegExp(`.{1,${max}}(?:\\s|$)`, 'g')) || [sentence] : [sentence]
    for (const part of parts) {
      if (current && `${current} ${part}`.length > max) { chunks.push(current); current = part.trim() }
      else current = current ? `${current} ${part}`.trim() : part.trim()
    }
  }
  if (current) chunks.push(current)
  return chunks
}
function detectSpeechLang(text) {
  if (/[\u0600-\u06ff]/.test(text)) return SPEECH_CODES.ar
  if (/\b(le|la|les|des|une|un|est|vous|nous|avec|pour|dans|sur|pas|que|qui)\b/i.test(text)) return SPEECH_CODES.fr
  return SPEECH_CODES.en
}
function pickVoice(voices, lang) {
  const base = lang.split('-')[0].toLowerCase()
  const candidates = voices.filter(voice => voice.lang.toLowerCase().startsWith(base))
  if (!candidates.length) return null
  const score = voice => {
    let value = 0
    const name = voice.name.toLowerCase()
    if (voice.lang.toLowerCase() === lang.toLowerCase()) value += 4
    if (/natural|neural|premium|enhanced|siri|google/.test(name)) value += 4
    if (/microsoft|apple|google/.test(name)) value += 1
    if (voice.localService) value += 1
    if (/espeak|compact|robotic/.test(name)) value -= 5
    return value
  }
  return [...candidates].sort((a, b) => score(b) - score(a))[0]
}

function Dialog({ title, children, onClose, className = '', t }) {
  const ref = useRef(null)
  const titleId = useId()
  useEffect(() => {
    const previous = document.activeElement
    const panel = ref.current
    const first = panel?.querySelector('button, input, textarea, select, [tabindex="0"]')
    ;(first || panel)?.focus()
    return () => previous?.focus?.()
  }, [])
  function keyboard(event) {
    if (event.key === 'Escape') { event.stopPropagation(); onClose() }
    if (event.key !== 'Tab') return
    const items = [...ref.current.querySelectorAll('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), a[href], iframe, [tabindex="0"]')].filter(el => el.getClientRects().length)
    const first = items[0]
    const last = items[items.length - 1]
    if (!first) { event.preventDefault(); return }
    if (event.shiftKey && (document.activeElement === first || document.activeElement === ref.current)) { event.preventDefault(); last.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
  }
  return <div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
    <section ref={ref} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1} onKeyDown={keyboard} className={`dialog ${className}`}>
      <header className="dialog-header"><div><span className="eyebrow">PROXYPAL / WORKSPACE</span><h2 id={titleId}>{title}</h2></div><IconButton icon="close" label={t('closeWindow')} onClick={onClose} /></header>
      {children}
    </section>
  </div>
}

function Progress({ value, label, threshold, t }) {
  const percent = percentage(value)
  return <div className="progress" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(percent)}>
    <span className="progress-fill" style={{ width: `${percent}%` }} />
    {threshold && <span className="progress-threshold" style={{ left: `${percentage(threshold * 100)}%` }} title={t('switchThreshold', { percent: Math.round(threshold * 100) })} />}
  </div>
}
function RateLimit({ name, rate, t, locale }) {
  if (!rate) return null
  const date = rate.reset_at ? new Date(typeof rate.reset_at === 'number' ? (rate.reset_at < 1e12 ? rate.reset_at * 1000 : rate.reset_at) : rate.reset_at) : null
  return <div className="rate-line"><span>{name}</span><bdi>{number(rate.remaining)} / {number(rate.limit)}</bdi>{date && !Number.isNaN(date.getTime()) && <small>{t('refreshAt', { time: new Intl.DateTimeFormat(localeInfo(locale).date, { hour: '2-digit', minute: '2-digit' }).format(date) })}</small>}</div>
}
function KeyStats({ item, t, locale }) {
  return <div className="key-stats">
    <div className="stat-line"><span>{t('localTokens')} {item.estimated_tokens > 0 && <small title={t('estimatedHint')}>· {t('estimatedPartial')}</small>}</span><bdi>{number(item.tokens)} / {number(item.token_budget)}</bdi></div>
    <Progress label={t('tokenBudgetProgress')} value={item.token_percent} threshold={item.threshold || 0.9} t={t} />
    <div className="stat-line"><span>{t('localRequestsLabel')}</span><bdi>{number(item.requests)} / {number(item.request_budget)}</bdi></div>
    <Progress label={t('requestBudgetProgress')} value={item.request_percent} threshold={item.threshold || 0.9} t={t} />
    <div className="rate-limits"><RateLimit name={t('providerTokensRemaining')} rate={item.rate_limits?.tokens} t={t} locale={locale} /><RateLimit name={t('providerRequestsRemaining')} rate={item.rate_limits?.requests} t={t} locale={locale} /></div>
  </div>
}

function PoolCard({ pool, connection, onSettings, t, locale }) {
  const [open, setOpen] = useState(false)
  const keys = pool.keys || []
  const active = keys.find(k => k.id === pool.active_id)
  const next = keys.find(k => k.id === pool.next_id)
  const currentPercent = percentage(active?.token_percent)
  const requestPercent = percentage(active?.request_percent)
  const threshold = active?.threshold || 0.9
  const hudId = useId()
  return <div className={`pool-card ${open ? 'hud-open' : ''}`}
    onMouseEnter={() => { if (window.matchMedia('(hover: hover)').matches) setOpen(true) }}
    onMouseLeave={e => { if (!e.currentTarget.contains(document.activeElement)) setOpen(false) }}
    onFocusCapture={e => { if (!e.currentTarget.contains(e.relatedTarget)) setOpen(true) }}
    onBlurCapture={e => { if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false) }}>
    <div className="pool-card-top"><span><Icon name="layers" size={16} /> {t('apiPool')}</span><span className={`connection-dot ${connection === 'online' ? 'connected' : ''}`} title={connection === 'online' ? t('gatewayConnected') : t('gatewayDisconnected')} /></div>
    <button type="button" className="pool-trigger" onClick={() => setOpen(true)} aria-expanded={open} aria-controls={hudId} aria-label={t('showPoolDetails')} onKeyDown={e => { if (e.key === 'Escape') setOpen(false) }}>
      <div className="stat-line"><span>{t('activeKey')}</span><span className="state-tag">{active ? keyStateLabel(active, t) : t('noKey')}</span></div>
      <strong className="key-name" dir="auto">{active?.label || active?.provider || t('waitingReadyKey')}</strong>
      <div className="meter-head"><span>{t('tokens')}</span><bdi className="masked">{active?.masked_key || '—'}</bdi><bdi><b>{Math.round(currentPercent)}<small>%</small></b></bdi></div>
      <Progress label={t('tokenProgress')} value={currentPercent} threshold={threshold} t={t} />
      <div className="meter-foot"><span>{t('switchAt', { percent: Math.round(threshold * 100) })}</span><span>{t('localRequests')} {Math.round(requestPercent)}%</span></div>
      <div className="next-key"><Icon name="key" size={14} /><span>{t('next')} <b dir="auto">{next?.label || next?.provider || '—'}</b></span><span className="state-tag">{next ? keyStateLabel(next, t) : t('noKey')}</span></div>
    </button>
    <p className="budget-note">{t('localBudgetNote')}</p>
    <button type="button" className="pool-manage" onClick={onSettings}><span>{t('manageKeys')}</span><Icon name="settings" size={15} /></button>
    <section className="pool-hud" id={hudId} aria-label={t('poolDetails')} onKeyDown={e => { if (e.key === 'Escape') { setOpen(false); e.currentTarget.closest('.pool-card')?.querySelector('.pool-manage')?.focus() } }}>
      <div className="section-heading"><h3>{t('keysStatus')}</h3><span>{t('keysSummary', { count: keys.length, switches: number(pool.switch_count) })}</span><IconButton icon="close" label={t('hidePoolDetails')} onClick={e => { setOpen(false); e.currentTarget.closest('.pool-card')?.querySelector('.pool-trigger')?.focus() }} /></div>
      <p className="muted">{t('poolRoutingNote')} · {t('strategyLabel')}: {t(`strategy_${pool.strategy || 'sticky'}`)}</p>
      {keys.length ? <div className="hud-key-list">{keys.map(k => <div className="hud-key" key={k.id}><div className="stat-line"><strong dir="auto">{k.label || k.provider}</strong><span className="state-tag">{keyStateLabel(k, t)}</span></div><small><bdi>{k.provider} · {k.masked_key}</bdi></small><KeyStats item={k} t={t} locale={locale} />{k.cooldown_until > 0 && <small>{t('stateCooldown')} · {new Intl.DateTimeFormat(localeInfo(locale).date, { hour: '2-digit', minute: '2-digit' }).format(new Date(typeof k.cooldown_until === 'number' && k.cooldown_until < 1e12 ? k.cooldown_until * 1000 : k.cooldown_until))}</small>}</div>)}</div> : <p className="empty-hint">{t('addKeyFromSettings')}</p>}
      <button className="button subtle" type="button" onClick={onSettings}><Icon name="settings" size={16} /> {t('poolSettings')}</button>
    </section>
  </div>
}

function Companion({ pool, shape, status, switched, onHide, t }) {
  const active = pool.keys.find(k => k.id === pool.active_id)
  const preparing = active && Math.max(active.token_percent, active.request_percent) >= (active.threshold || 0.9) * 100 - 10
  const state = switched ? 'switched' : preparing ? 'preparing' : 'stable'
  const mood = switched ? 'switched' : preparing ? 'preparing' : status === 'thinking' ? 'thinking' : status === 'streaming' ? 'happy' : active ? 'idle' : 'sleepy'
  const labelKey = switched ? 'companionSwitched' : preparing ? 'companionPreparing' : active ? 'companionStable' : 'companionWaiting'
  const label = t(labelKey)
  return <div className={`companion-control companion-${state}`} role="status" aria-label={t('companionStatus', { state: label })}><Mascot shape={shape} mood={mood} size={28} className="companion-mascot" /><span>{label}</span><IconButton icon="close" label={t('hideCompanion')} onClick={onHide} /></div>
}

function KeyEditor({ item, onMutation, pending, t, locale }) {
  const [editing, setEditing] = useState(false)
  return <article className="existing-key">
    <div className="section-heading"><div><strong dir="auto">{item.label || item.provider}</strong><p className="masked"><bdi>{item.provider} · {item.masked_key}</bdi></p></div><span className="state-tag">{keyStateLabel(item, t)}</span></div>
    <KeyStats item={item} t={t} locale={locale} />
    <div className="key-meta">
      <span>{t('budgetPeriod')}: <b>{t(`period_${item.budget_period || 'never'}`)}</b></span>
      {item.last_error ? <span className="key-warning">{t('lastErrorLabel')}: {errorReasonLabel(item.last_error.reason, t)} · {item.last_error.status}
        {item.failures > 1 && ` · ${t('failureCount', { count: item.failures })}`}</span> : <span className="muted">{t('noLastError')}</span>}
    </div>
    <div className="button-row"><button className="button subtle" type="button" onClick={() => setEditing(v => !v)} aria-expanded={editing}><Icon name="pen" size={15} /> {t('editLimits')}</button><button className="button subtle" type="button" disabled={pending} onClick={() => onMutation(`/pool/keys/${encodeURIComponent(item.id)}`, 'PATCH', { enabled: !item.enabled })}>{item.enabled ? t('disableKey') : t('enableKey')}</button><button className="text-button" type="button" disabled={pending} onClick={() => {
      if (window.confirm(item.state === 'blocked' ? t('unblockConfirm') : t('resetConfirm'))) onMutation(`/pool/keys/${encodeURIComponent(item.id)}/reset`, 'POST', {})
    }}>{item.state === 'blocked' ? t('unblockKey') : t('resetCounter')}</button><button className="text-button danger-text" type="button" disabled={pending} onClick={() => {
      if (window.confirm(t('confirmDeleteKey', { name: item.label || item.provider }))) onMutation(`/pool/keys/${encodeURIComponent(item.id)}`, 'DELETE', undefined, t('keyDeleted'))
    }}><Icon name="trash" size={14} />{t('deleteKey')}</button></div>
    {editing && <KeySettingsForm item={item} pending={pending} t={t} onSave={async body => { if (await onMutation(`/pool/keys/${encodeURIComponent(item.id)}`, 'PATCH', body)) setEditing(false) }} />}
  </article>
}
function KeySettingsForm({ item, pending, onSave, t }) {
  const [draft, setDraft] = useState({ label: item.label || '', token_budget: item.token_budget || 100000, request_budget: item.request_budget || 1000, threshold: item.threshold || 0.9, budget_period: item.budget_period || 'never' })
  const update = e => setDraft(d => ({ ...d, [e.target.name]: ['label', 'budget_period'].includes(e.target.name) ? e.target.value : e.target.value === '' ? '' : Number(e.target.value) }))
  return <form className="key-edit-form" onSubmit={e => { e.preventDefault(); onSave(draft) }}>
    <label className="field">{t('keyName')}<input name="label" value={draft.label} onChange={update} maxLength={80} dir="auto" /></label>
    <div className="form-grid"><label className="field">{t('tokenBudget')}<input type="number" name="token_budget" value={draft.token_budget} onChange={update} min="1" step="1" required /></label><label className="field">{t('requestBudget')}<input type="number" name="request_budget" value={draft.request_budget} onChange={update} min="1" step="1" required /></label></div>
    <label className="field">{t('budgetPeriod')}<select name="budget_period" value={draft.budget_period} onChange={update}>{['never', 'daily', 'weekly', 'monthly'].map(period => <option key={period} value={period}>{t(`period_${period}`)}</option>)}</select></label>
    <label className="field">{t('switchThreshold', { percent: Math.round(draft.threshold * 100) })}<input name="threshold" type="range" min="0.5" max="1" step="0.01" value={draft.threshold} onChange={update} /></label>
    <button className="button primary" disabled={pending}>{t('saveChanges')}</button>
  </form>
}

function CodeBlock({ children, onCopy, onPreview, t }) {
  const codeElement = Array.isArray(children) ? children[0] : children
  const text = String(codeElement?.props?.children || '').replace(/\n$/, '')
  const language = /language-([^\s]+)/.exec(codeElement?.props?.className || '')?.[1] || 'text'
  return <div className="code-block" dir="ltr"><div className="code-toolbar"><span>{language}</span><div><button onClick={() => onCopy(text)} title={t('copyCode')}><Icon name="copy" size={14} /> {t('copy')}</button><button onClick={() => onPreview({ text, language })} title={t('preview')}><Icon name="eye" size={14} /> {t('preview')}</button><button onClick={() => downloadCode(text, language)} title={t('downloadCode')}><Icon name="download" size={14} /> {t('downloadCode')}</button></div></div><pre>{children}</pre></div>
}
function downloadCode(text, language) {
  const extensions = { javascript: 'js', typescript: 'ts', python: 'py', bash: 'sh', jsx: 'jsx', tsx: 'tsx', html: 'html', css: 'css', json: 'json', sql: 'sql', js: 'js', xml: 'xml', markdown: 'md' }
  const ext = extensions[language] || 'txt'
  download(text, `proxypal-code.${ext}`)
}
function cleanMarkdown(raw) {
  // Models sometimes emit a lone table delimiter row; it is not a table, so it would print as pipes and dashes.
  const lines = String(raw).split('\n')
  const kept = []
  let fence = null
  for (const line of lines) {
    const marker = /^\s*(```|~~~)/.exec(line)
    if (marker) {
      if (!fence) fence = marker[1]
      else if (fence === marker[1]) fence = null
      kept.push(line)
      continue
    }
    if (fence) { kept.push(line); continue }
    if (/^(?: {4}|\t)/.test(line)) { kept.push(line); continue }
    if (/^\s*\|?[\s:|-]+\|?\s*$/.test(line) && line.includes('|') && line.includes('-')) {
      const previous = kept[kept.length - 1] || ''
      if (!previous.includes('|')) continue
    }
    kept.push(line)
  }
  return kept.join('\n').replace(/^>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*$/gim,
    (_, kind) => `> **${kind.charAt(0)}${kind.slice(1).toLowerCase()}**`)
}
function Markdown({ text, onCopy, onPreview, t }) {
  return <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
    pre: ({ children }) => <CodeBlock onCopy={onCopy} onPreview={onPreview} t={t}>{children}</CodeBlock>,
    a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
  }}>{cleanMarkdown(text)}</ReactMarkdown>
}
function previewDocument({ text, language }) {
  const escape = value => value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  let body = `<pre style="white-space:pre-wrap;padding:24px">${escape(text)}</pre>`
  if (language === 'html' || /^\s*(<!doctype html|<html|<div|<main|<section)/i.test(text)) body = text
  else if (['javascript', 'js'].includes(language)) body = `<div id="app"></div><script>${text.replace(/<\/script/gi, '<\\/script')}</script>`
  else if (language === 'css') body = `<style>${text.replace(/<\/style/gi, '<\\/style')}</style><main><h1>ProxyPal Preview</h1><p>CSS preview</p><button>Button</button></main>`
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body>${body}</body></html>`
}

function ModelPicker({ providers, pool, value, onChange, disabled, modelHealth, testingModel, onUpdate, updating, t }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const rootRef = useRef(null)
  const searchRef = useRef(null)
  const triggerRef = useRef(null)
  const menuId = useId()
  const listId = useId()
  const health = useMemo(() => providerHealth(pool), [pool])
  const options = useMemo(() => modelOptions(providers, health, value, modelHealth, testingModel), [providers, health, value, modelHealth, testingModel])
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return options
    return options.filter(option => option.id.toLowerCase().includes(q) || option.providers.some(name => name.toLowerCase().includes(q)))
  }, [options, query])
  const selected = options.find(option => option.id === value)
  useEffect(() => {
    if (!open) return
    const outside = event => { if (!rootRef.current?.contains(event.target)) setOpen(false) }
    document.addEventListener('pointerdown', outside)
    return () => document.removeEventListener('pointerdown', outside)
  }, [open])
  useEffect(() => { setActive(0) }, [query])
  useEffect(() => {
    if (!open) return
    setQuery('')
    const index = options.findIndex(option => option.id === value)
    setActive(index > -1 ? index : 0)
    requestAnimationFrame(() => searchRef.current?.focus())
    // Options refresh periodically; only re-initialize when the menu opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])
  function choose(id) { onChange(id); setOpen(false); triggerRef.current?.focus() }
  function onKeyDown(event) {
    if (event.key === 'ArrowDown') { event.preventDefault(); setActive(index => Math.min(filtered.length - 1, index + 1)) }
    else if (event.key === 'ArrowUp') { event.preventDefault(); setActive(index => Math.max(0, index - 1)) }
    else if (event.key === 'Enter') { event.preventDefault(); const option = filtered[active]; if (option) choose(option.id) }
    else if (event.key === 'Escape') { event.preventDefault(); setOpen(false); triggerRef.current?.focus() }
  }
  return <div className="model-picker" ref={rootRef}>
    <button ref={triggerRef} type="button" className="model-trigger" aria-haspopup="listbox" aria-expanded={open} aria-controls={menuId} aria-label={`${t('openModelPicker')}: ${value || t('modelNoKeys')}`} disabled={disabled} onClick={() => setOpen(v => !v)}>
      <span className={`model-dot ${selected?.status || 'off'}`} />
      <span className="model-trigger-label" dir="ltr">{value || t('modelNoKeys')}</span>
      <Icon name={open ? 'chevronUp' : 'chevron'} size={15} />
    </button>
    {open && <div className="model-menu" id={menuId}>
      <div className="model-menu-head"><Icon name="search" size={16} /><input ref={searchRef} role="combobox" aria-expanded="true" aria-controls={listId} aria-autocomplete="list" aria-label={t('modelSearch')} placeholder={t('modelSearch')} value={query} onChange={e => setQuery(e.target.value)} onKeyDown={onKeyDown} /><IconButton icon="refresh" className={`model-update ${updating ? 'is-busy' : ''}`} label={updating ? t('modelsUpdating') : t('updateModels')} disabled={updating} onClick={onUpdate} /><IconButton icon="close" label={t('closeModelPicker')} onClick={() => { setOpen(false); triggerRef.current?.focus() }} /></div>
      <p className="model-legend"><span className="model-dot ready" />{t('modelReady')}<span className="model-dot unknown" />{t('modelUntested')}<span className="model-dot limited" />{t('modelLimited')}</p>
      <div className="model-list" role="listbox" id={listId} aria-label={t('model')}>
        {filtered.length ? filtered.map((option, index) => <button key={option.id} type="button" role="option" aria-selected={option.id === value} className={`model-option ${index === active ? 'active' : ''}`} onMouseEnter={() => setActive(index)} onClick={() => choose(option.id)}>
          <span className={`model-dot ${option.status}`} title={modelStatusTitle(option, t)} />
          <span className="model-option-main"><bdi>{option.id}</bdi><small>{option.providers.join(' · ') || t('modelNoKeys')}</small></span>
          {option.status !== 'unknown' && <span className={`model-ready-label ${option.status}`}>{t(option.status === 'ready' ? 'modelReady' : option.status === 'limited' ? 'modelLimited' : 'modelTesting')}</span>}
          {option.id === value && <Icon name="check" size={15} />}
        </button>) : <p className="empty-hint">{t('modelEmpty')}</p>}
      </div>
    </div>}
  </div>
}

function normalizePreferences(raw) {
  const p = raw && typeof raw === 'object' ? raw : {}
  return {
    locale: locales[p.locale] ? p.locale : 'ar',
    theme: themes.includes(p.theme) ? p.theme : 'light',
    font: fonts.some(item => item.id === p.font) ? p.font : 'plex',
    selectedModel: typeof p.selectedModel === 'string' ? p.selectedModel : '',
    agent: AGENTS.some(item => item.id === p.agent) ? p.agent : 'general',
    temperature: typeof p.temperature === 'number' ? p.temperature : 0.7,
    topP: typeof p.topP === 'number' ? p.topP : 1,
    systemInstructions: typeof p.systemInstructions === 'string' ? p.systemInstructions : '',
    userName: typeof p.userName === 'string' ? p.userName : '',
    avatar: ['initial', ...AVATARS].includes(p.avatar) ? p.avatar : 'initial',
    mascot: ['orb', 'robot', 'cat', 'hidden'].includes(p.mascot) ? p.mascot : 'orb',
    sound: typeof p.sound === 'boolean' ? p.sound : true,
    workspacePath: typeof p.workspacePath === 'string' ? p.workspacePath : '',
    voiceLang: ['auto', 'ar', 'en', 'fr'].includes(p.voiceLang) ? p.voiceLang : 'auto',
    voiceURI: typeof p.voiceURI === 'string' ? p.voiceURI : '',
    voiceRate: typeof p.voiceRate === 'number' && p.voiceRate >= 0.5 && p.voiceRate <= 1.6 ? p.voiceRate : 0.95,
    voicePitch: typeof p.voicePitch === 'number' && p.voicePitch >= 0.6 && p.voicePitch <= 1.4 ? p.voicePitch : 1,
  }
}

export default function App() {
  const boot = useMemo(() => normalizePreferences(readStored(PREFS, {})), [])
  const [preferences, setPreferences] = useState(boot)
  const { locale, theme, font, selectedModel, agent, temperature, topP, systemInstructions, userName, avatar, mascot, sound, voiceLang, voiceURI, voiceRate, voicePitch } = preferences
  const t = useMemo(() => translator(locale), [locale])
  const [onboarded, setOnboarded] = useState(() => {
    try { return localStorage.getItem(ONBOARDED) === '1' } catch { return true }
  })
  const [splash, setSplash] = useState(true)
  const [splashLeaving, setSplashLeaving] = useState(false)
  const [onboardName, setOnboardName] = useState(() => boot.userName)
  const [onboardAvatar, setOnboardAvatar] = useState(() => boot.avatar === 'initial' ? AVATARS[0] : boot.avatar)
  const [conversations, setConversations] = useState(() => loadConversations(t))
  const [activeId, setActiveId] = useState(() => {
    const saved = readStored(STORE, [])
    const stored = localStorage.getItem(ACTIVE)
    if (Array.isArray(saved) && stored && saved.some(c => c.id === stored)) return stored
    return Array.isArray(saved) ? saved[0]?.id || '' : ''
  })
  const conversation = conversations.find(c => c.id === activeId) || conversations[0]
  const messages = conversation.messages
  const conversationId = conversation.id
  const [input, setInput] = useState('')
  const [attachments, setAttachments] = useState([])
  const [readingFiles, setReadingFiles] = useState(false)
  const [status, setStatus] = useState('idle')
  const busy = status !== 'idle'
  const [providers, setProviders] = useState([])
  const [pool, setPool] = useState({ keys: [] })
  const [modelHealth, setModelHealth] = useState({})
  const [testingModel, setTestingModel] = useState('')
  const [modelsUpdating, setModelsUpdating] = useState(false)
  const [connection, setConnection] = useState('connecting')
  const [staleGateway, setStaleGateway] = useState(false)
  const [online, setOnline] = useState(navigator.onLine)
  const [sidebarOpen, setSidebarOpen] = useState(() => !window.matchMedia('(max-width: 900px)').matches)
  const [focusMode, setFocusMode] = useState(false)
  const [search, setSearch] = useState('')
  const [settings, setSettings] = useState(null)
  const [codePreview, setCodePreview] = useState(null)
  const [previewTab, setPreviewTab] = useState('preview')
  const [editingId, setEditingId] = useState(null)
  const [editText, setEditText] = useState('')
  const [renamingId, setRenamingId] = useState(null)
  const [renameText, setRenameText] = useState('')
  const [audioEnabled, setAudioEnabled] = useState(false)
  const [voices, setVoices] = useState([])
  const [speakingId, setSpeakingId] = useState(null)
  const [listening, setListening] = useState(false)
  const [notice, setNotice] = useState(null)
  const [storageWarning, setStorageWarning] = useState(false)
  const [poolPending, setPoolPending] = useState(false)
  const [pollRevision, setPollRevision] = useState(0)
  const [keyInput, setKeyInput] = useState('')
  const [showKeys, setShowKeys] = useState(false)
  const [provider, setProvider] = useState('groq')
  const [showAllProviders, setShowAllProviders] = useState(false)
  const [keyLabel, setKeyLabel] = useState('')
  const [tokenBudget, setTokenBudget] = useState(100000)
  const [requestBudget, setRequestBudget] = useState(1000)
  const [providerName, setProviderName] = useState('')
  const [providerUrl, setProviderUrl] = useState('')
  const [providerModels, setProviderModels] = useState('')
  const [modelDraft, setModelDraft] = useState({})
  const [workspaceContext, setWorkspaceContext] = useState(null)
  const [workspaceLoading, setWorkspaceLoading] = useState(false)
  const [workspaceRoot, setWorkspaceRoot] = useState('')
  const [switchedRecently, setSwitchedRecently] = useState(false)
  const switchTimer = useRef(null)
  useEffect(() => () => clearTimeout(switchTimer.current), [])
  const sendLock = useRef(false)
  const streamController = useRef(null)
  const abortReason = useRef('')
  const recognition = useRef(null)
  const chatRef = useRef(null)
  const inputRef = useRef(null)
  const fileRef = useRef(null)
  const noticeTimer = useRef(null)
  const persistenceTimer = useRef(null)
  const pendingPersistence = useRef(null)
  const nearBottom = useRef(true)
  const mounted = useRef(true)
  const speechToken = useRef(0)
  const probedModels = useRef(new Set())
  const lastMascot = useRef(mascot === 'hidden' ? 'orb' : mascot)
  useEffect(() => { if (mascot !== 'hidden') lastMascot.current = mascot }, [mascot])
  const soundContext = useRef(null)
  const workspaceRootFetched = useRef(false)

  const playSound = useCallback(kind => {
    if (!sound) return
    const AudioCtor = window.AudioContext || window.webkitAudioContext
    if (!AudioCtor) return
    try {
      const context = soundContext.current || (soundContext.current = new AudioCtor())
      if (context.state === 'suspended') context.resume().catch(() => {})
      const patterns = {
        send: [[523.25, 0, .09, .028], [783.99, .055, .12, .024]],
        done: [[659.25, 0, .11, .026], [987.77, .09, .18, .02]],
        switch: [[440, 0, .1, .026], [587.33, .075, .1, .024], [880, .15, .22, .02]],
        error: [[233.08, 0, .14, .024], [174.61, .1, .2, .022]],
      }
      for (const [frequency, offset, duration, peak] of patterns[kind] || []) {
        const start = context.currentTime + offset
        const oscillator = context.createOscillator()
        const envelope = context.createGain()
        oscillator.type = kind === 'error' ? 'triangle' : 'sine'
        oscillator.frequency.setValueAtTime(frequency, start)
        envelope.gain.setValueAtTime(0, start)
        envelope.gain.linearRampToValueAtTime(peak, start + .012)
        envelope.gain.exponentialRampToValueAtTime(.0001, start + duration)
        oscillator.connect(envelope).connect(context.destination)
        oscillator.start(start)
        oscillator.stop(start + duration + .02)
      }
    } catch { /* A muted or blocked audio context must never stop a request. */ }
  }, [sound])
  useEffect(() => {
    if (settings !== 'general' || workspaceRootFetched.current) return
    workspaceRootFetched.current = true
    fetch(`${GW}/workspace/root`, { headers: authHeaders() })
      .then(response => response.ok ? response.json() : null)
      .then(data => {
        if (!data?.root) return
        setWorkspaceRoot(data.root)
        setPreferences(p => p.workspacePath.trim() ? p : { ...p, workspacePath: data.root })
      })
      .catch(() => { /* A gateway without a folder root keeps the manual path. */ })
  }, [settings])

  const displayName = userName.trim() || t('defaultUserName')
  const customProviders = (providers || []).filter(item => item.custom)
  const providerIds = [...PROVIDER_CATALOG.map(item => item.id), ...customProviders.map(item => item.provider)]

  function pref(name, value) { setPreferences(p => ({ ...p, [name]: value })) }
  function completeOnboarding(event) {
    event.preventDefault()
    const name = onboardName.trim()
    if (!name) return
    setPreferences(p => ({ ...p, userName: name, avatar: onboardAvatar }))
    updateMessages(conversationId, list => [...list, { id: uid(), role: 'assistant', content: t('helloName', { name }) }])
    try { localStorage.setItem(ONBOARDED, '1') } catch { /* preferences already persist the profile */ }
    setOnboarded(true)
    requestAnimationFrame(() => inputRef.current?.focus())
  }
  function notify(text, error = false) {
    clearTimeout(noticeTimer.current)
    setNotice({ text, error })
    noticeTimer.current = setTimeout(() => setNotice(null), 5500)
  }
  function updateMessages(id, updater) {
    if (!mounted.current) return
    setConversations(previous => previous.map(c => {
      if (c.id !== id) return c
      const next = typeof updater === 'function' ? updater(c.messages) : updater
      const title = textOf(next.find(m => m.role === 'user') || { content: '' }).slice(0, 45) || next.find(m => m.attachments?.length)?.attachments[0]?.name || t('newChat')
      return { ...c, messages: next, title, updatedAt: Date.now() }
    }))
  }
  function applyStatus(data) {
    // A gateway started before an update answers without a version; that is exactly the stale case.
    setStaleGateway(Number(data.version) !== GATEWAY_VERSION)
    const healthMap = data.model_health && typeof data.model_health === 'object' ? data.model_health : null
    if (healthMap) setModelHealth(previous => ({ ...previous, ...healthMap }))
    if (Array.isArray(data.providers)) {
      setProviders(data.providers)
      const nextPool = data.pool && Array.isArray(data.pool.keys) ? data.pool : pool
      if (data.pool && Array.isArray(data.pool.keys)) setPool(data.pool)
      const options = modelOptions(data.providers, providerHealth(nextPool), '', healthMap || {})
      const ids = options.map(option => option.id)
      setPreferences(p => {
        if (p.selectedModel && ids.includes(p.selectedModel)) return p
        const available = options.filter(option => option.status !== 'limited')
        // A model already proven to answer is a safer first pick than list order.
        const preferred = (available.find(option => option.health?.ok === true) || available[0])?.id || ''
        return preferred === p.selectedModel ? p : { ...p, selectedModel: preferred }
      })
    } else if (data.pool && Array.isArray(data.pool.keys)) setPool(data.pool)
  }

  async function probeModel(model) {
    if (!model) return
    setTestingModel(model)
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 25000)
    try {
      const response = await fetch(`${GW}/models/probe`, { method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify({ model }), signal: controller.signal })
      // An older gateway has no probe route; leave the model untested rather than inventing a status.
      if (response.status === 404) return
      const data = await response.json().catch(() => null)
      if (!data || typeof data.ok !== 'boolean') return
      if (!mounted.current) return
      setModelHealth(previous => ({ ...previous, [model]: {
        ok: data.ok, at: Date.now() / 1000, latency_ms: data.latency_ms,
        reason: data.reason || (data.ok ? null : 'probe'), status: data.status ?? null,
      } }))
      if (!data.ok) notify(t('probeFailed'), true)
    } catch (error) {
      if (mounted.current && error.name !== 'AbortError') notify(t('probeUnreachable'), true)
    } finally {
      clearTimeout(timeout)
      if (mounted.current) setTestingModel(current => current === model ? '' : current)
    }
  }

  async function updateModels() {
    if (modelsUpdating) return
    setModelsUpdating(true)
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 70000)
    try {
      const response = await fetch(`${GW}/models/refresh`, {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ model: selectedModel }),
        signal: controller.signal,
      })
      const data = await response.json().catch(() => null)
      if (!response.ok || !data) throw new Error(t('errorGateway'))
      applyStatus(data)
      // A refresh can retire stale failures; replace instead of merging them back.
      if (data.model_health) setModelHealth(data.model_health)
      setPollRevision(value => value + 1)
      const summary = data.refresh || {}
      notify(t('modelsUpdated', { ok: summary.ok || 0, failed: summary.failed || 0, skipped: summary.skipped || 0 }))
    } catch (error) {
      notify(error.name === 'AbortError' ? t('modelsUpdateTimeout') : t('modelsUpdateFail'), true)
    } finally {
      clearTimeout(timeout)
      if (mounted.current) setModelsUpdating(false)
    }
  }

  useEffect(() => {
    if (!selectedModel || connection !== 'online' || busy || testingModel) return
    if (probedModels.current.has(selectedModel)) return
    const record = modelHealthRecord(modelHealth, selectedModel)
    if (record && record.age <= (record.ok === true ? MODEL_OK_TTL : MODEL_FAIL_TTL)) return
    probedModels.current.add(selectedModel)
    probeModel(selectedModel)
    // Testing the selected model must not restart for unrelated re-renders.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedModel, connection, busy, modelHealth, testingModel])

  useEffect(() => {
    const info = localeInfo(locale)
    document.documentElement.lang = locale
    document.documentElement.dir = info.dir
    document.title = `${t('appName')} · ${t('tagline')}`
  }, [locale, t])
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.documentElement.dataset.font = font
    document.documentElement.style.colorScheme = darkThemes.has(theme) ? 'dark' : 'light'
    const canvas = getComputedStyle(document.documentElement).getPropertyValue('--canvas').trim()
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', canvas || '#f9f9f9')
  }, [theme, font])
  useEffect(() => {
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const hold = reduced ? 250 : 1400
    const leaving = setTimeout(() => setSplashLeaving(true), hold)
    const done = setTimeout(() => setSplash(false), hold + (reduced ? 150 : 550))
    return () => { clearTimeout(leaving); clearTimeout(done) }
  }, [])
  useEffect(() => {
    const timer = setTimeout(() => {
      try { localStorage.setItem(PREFS, JSON.stringify(preferences)) } catch { setStorageWarning(true) }
    }, 100)
    return () => clearTimeout(timer)
  }, [preferences])
  useEffect(() => {
    const ordered = conversationOrder(conversations)
    pendingPersistence.current = ordered.map(c => ({ ...c, messages: c.messages.map(m => m.streaming ? { ...m, streaming: false, incomplete: true } : m) }))
    // Throttle rather than debounce: continuous token delivery must still persist partial replies.
    if (!persistenceTimer.current) persistenceTimer.current = setTimeout(() => {
      persistenceTimer.current = null
      try { localStorage.setItem(STORE, JSON.stringify(pendingPersistence.current)) } catch { setStorageWarning(true) }
    }, 500)
  }, [conversations, conversationId])
  useEffect(() => {
    try { localStorage.setItem(ACTIVE, conversationId) } catch { /* storage errors surface through the conversation store */ }
  }, [conversationId])
  useEffect(() => {
    const flush = () => {
      if (!pendingPersistence.current) return
      try { localStorage.setItem(STORE, JSON.stringify(pendingPersistence.current)) } catch { /* The live persistence timer shows storage errors. */ }
    }
    window.addEventListener('pagehide', flush)
    return () => { clearTimeout(persistenceTimer.current); persistenceTimer.current = null; flush(); window.removeEventListener('pagehide', flush) }
  }, [])
  useEffect(() => {
    const on = () => setOnline(true)
    const off = () => { setOnline(false); setConnection('offline') }
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => { window.removeEventListener('online', on); window.removeEventListener('offline', off) }
  }, [])
  useEffect(() => {
    let cancelled = false
    let timer
    let timeout
    let controller
    async function refresh() {
      if (cancelled) return
      const started = Date.now()
      if (online) {
        controller = new AbortController()
        timeout = setTimeout(() => controller.abort(), busy ? 1900 : 4500)
        try {
          const response = await fetch(`${GW}/status?model=${encodeURIComponent(selectedModel)}`, { signal: controller.signal, cache: 'no-store', headers: authHeaders() })
          if (!response.ok) throw new Error('Status unavailable')
          const data = await response.json()
          if (!cancelled) { applyStatus(data); setConnection('online') }
        } catch { if (!cancelled) setConnection('offline') }
        finally { clearTimeout(timeout) }
      } else setConnection('offline')
      if (!cancelled) timer = setTimeout(refresh, Math.max(0, (busy ? 2000 : 5000) - (Date.now() - started)))
    }
    refresh()
    return () => { cancelled = true; clearTimeout(timer); clearTimeout(timeout); controller?.abort() }
    // Polling must not restart when applyStatus gets a new identity on each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedModel, busy, online, pollRevision])
  useEffect(() => {
    if (chatRef.current && nearBottom.current && !search) chatRef.current.scrollTop = chatRef.current.scrollHeight
  }, [messages, status, search])
  useEffect(() => {
    nearBottom.current = true
    if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight
  }, [conversationId])
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      streamController.current?.abort()
      recognition.current?.abort()
      window.speechSynthesis?.cancel()
      clearTimeout(noticeTimer.current)
    }
  }, [])
  useEffect(() => {
    if (!window.speechSynthesis) return
    const load = () => { if (mounted.current) setVoices(window.speechSynthesis.getVoices()) }
    load()
    window.speechSynthesis.addEventListener?.('voiceschanged', load)
    return () => window.speechSynthesis.removeEventListener?.('voiceschanged', load)
  }, [])

  function cancelSpeech() { speechToken.current++; window.speechSynthesis?.cancel(); setSpeakingId(null) }
  function toggleAudio() {
    if (audioEnabled) cancelSpeech()
    setAudioEnabled(v => !v)
  }
  function speakText(rawText, id, forcedLang) {
    if (!window.speechSynthesis || !window.SpeechSynthesisUtterance) { notify(t('voiceUnavailable'), true); return }
    cancelSpeech()
    const text = speechText(rawText)
    if (!text) return
    const lang = forcedLang || (voiceLang === 'auto' ? detectSpeechLang(text) : SPEECH_CODES[voiceLang])
    const base = lang.split('-')[0].toLowerCase()
    const chosen = voices.find(voice => voice.voiceURI === voiceURI && voice.lang.toLowerCase().startsWith(base)) || pickVoice(voices, lang)
    if (!chosen) notify(t('voiceNoMatch'), true)
    const chunks = speechChunks(text)
    const token = ++speechToken.current
    let index = 0
    if (id) setSpeakingId(id)
    const next = () => {
      if (token !== speechToken.current) return
      if (index >= chunks.length) { if (id) setSpeakingId(null); return }
      const utterance = new SpeechSynthesisUtterance(chunks[index++])
      utterance.lang = chosen?.lang || lang
      if (chosen) utterance.voice = chosen
      utterance.rate = voiceRate
      utterance.pitch = voicePitch
      utterance.onend = next
      utterance.onerror = event => {
        if (token !== speechToken.current) return
        if (id) setSpeakingId(null)
        if (!['canceled', 'interrupted'].includes(event.error)) notify(t('voiceUnavailable'), true)
      }
      window.speechSynthesis.speak(utterance)
    }
    next()
  }
  function readResponse(message) {
    if (!audioEnabled) return
    if (speakingId === message.id) { cancelSpeech(); return }
    speakText(textOf(message), message.id)
  }
  function testVoice() {
    const lang = voiceLang === 'auto' ? localeInfo(locale).speech : SPEECH_CODES[voiceLang]
    speakText(t('voiceTestText'), null, lang)
  }
  function toggleVoice() {
    if (recognition.current) { recognition.current.stop(); return }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) { notify(t('micUnavailable'), true); return }
    const instance = new SR()
    recognition.current = instance
    instance.lang = voiceLang === 'auto' ? localeInfo(locale).speech : SPEECH_CODES[voiceLang]
    instance.interimResults = false
    instance.onresult = e => { if (mounted.current) setInput(previous => [previous, e.results[0][0].transcript].filter(Boolean).join(' ')) }
    instance.onend = () => { recognition.current = null; if (mounted.current) setListening(false) }
    instance.onerror = e => { if (mounted.current && !['aborted', 'no-speech'].includes(e.error)) notify(t('micPermission'), true) }
    try { instance.start(); setListening(true) } catch { recognition.current = null; notify(t('micStart'), true) }
  }
  async function copy(text) {
    try { await navigator.clipboard.writeText(text); notify(t('copied')) } catch { notify(t('copyFailed'), true) }
  }
  async function attachFiles(event) {
    const files = [...event.target.files]
    event.target.value = ''
    if (!files.length || readingFiles || sendLock.current) return
    setReadingFiles(true)
    try {
      const loaded = []
      for (const file of files) {
        if (file.size > 8 * 1024 * 1024) throw new Error(t('attachmentLarge'))
        if (file.type.startsWith('image/')) loaded.push({ id: uid(), kind: 'image', name: file.name, url: await fileData(file, t) })
        else {
          const sample = new Uint8Array(await file.slice(0, 4096).arrayBuffer())
          if (sample.includes(0) || /\.(pdf|docx?|xlsx?|zip|exe)$/i.test(file.name)) throw new Error(t('attachmentBinary'))
          loaded.push({ id: uid(), kind: 'text', name: file.name, text: await file.text() })
        }
      }
      if (mounted.current) setAttachments(a => [...a, ...loaded])
    } catch (error) { notify(error.message, true) }
    finally { if (mounted.current) setReadingFiles(false) }
  }

  async function send(overrideMessages) {
    if (sendLock.current || readingFiles) return
    if (!selectedModel) { notify(t('errorAddKeyModel'), true); return }
    if (!overrideMessages && !input.trim() && !attachments.length) return
    sendLock.current = true
    playSound('send')
    recognition.current?.abort()
    cancelSpeech()
    abortReason.current = ''
    const controller = new AbortController()
    streamController.current = controller
    const id = conversationId
    const assistantId = uid()
    // Attachments are the canonical, full request data; derive multimodal content at send time.
    const userMessage = { id: uid(), role: 'user', content: input.trim(), attachments }
    const base = overrideMessages || [...messages, userMessage]
    const assistant = { id: assistantId, role: 'assistant', content: '', reasoning: '', model: selectedModel, streaming: true }
    updateMessages(id, [...base, assistant])
    if (!overrideMessages) {
      setInput('')
      setAttachments([])
      // Keep the caret in the composer while the reply streams.
      inputRef.current?.focus()
    }
    setEditingId(null)
    setSearch('')
    nearBottom.current = true
    setStatus('thinking')
    let inactivityTimer
    let reader
    let content = ''
    let reasoning = ''
    let usedModel = selectedModel
    let substitutedFrom = null
    let switchAnnounced = false
    let gateway = null
    let usage = null
    let context = null
    let completed = false
    let buffer = ''
    const armTimeout = () => {
      clearTimeout(inactivityTimer)
      inactivityTimer = setTimeout(() => { abortReason.current = 'timeout'; controller.abort() }, INACTIVITY_MS)
    }
    const patch = extra => updateMessages(id, current => current.map(m => m.id === assistantId ? { ...m, content, reasoning, model: usedModel, substituted: substitutedFrom, gateway, usage, context, ...extra } : m))
    function processEvent(event) {
      const data = event.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n').trim()
      if (!data) return
      if (data === '[DONE]') { completed = true; return }
      let json
      try { json = JSON.parse(data) } catch { throw new Error(t('errorInvalidEvent')) }
      if (json.error) throw new Error(errorText(json.error, t))
      if (json._gateway) {
        const eventGateway = json._gateway
        gateway = { key_id: eventGateway.key_id, provider: eventGateway.provider, label: eventGateway.label, model: eventGateway.model, switched: eventGateway.switched }
        if (eventGateway.switched && !switchAnnounced) {
          switchAnnounced = true
          playSound('switch')
          setSwitchedRecently(true)
          clearTimeout(switchTimer.current)
          switchTimer.current = setTimeout(() => setSwitchedRecently(false), 5000)
        }
        if (eventGateway.model) {
          if (selectedModel && eventGateway.model !== selectedModel) substitutedFrom = selectedModel
          usedModel = eventGateway.model
        }
        if (eventGateway.context) context = eventGateway.context
        if (eventGateway.pool && mounted.current) setPool(eventGateway.pool)
      }
      if (json.model) usedModel = json.model
      if (json.usage) usage = json.usage
      const choice = json.choices?.[0]
      const delta = choice?.delta
      if (typeof delta?.content === 'string') content += delta.content
      if (typeof delta?.reasoning === 'string') reasoning += delta.reasoning
      else if (typeof delta?.reasoning_content === 'string') reasoning += delta.reasoning_content
      else if (Array.isArray(delta?.reasoning_details)) reasoning += delta.reasoning_details.map(r => r.text || '').join('')
      if (typeof choice?.message?.content === 'string' && !content) content = choice.message.content
      patch({ streaming: true })
    }
    function consumeBuffer(flush = false) {
      let boundary
      while ((boundary = buffer.indexOf('\n\n')) !== -1 && !completed) {
        const event = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        processEvent(event)
      }
      if (flush && buffer.trim() && !completed) { processEvent(buffer); buffer = '' }
    }
    try {
      armTimeout()
      const agentPrompt = AGENTS.find(item => item.id === agent)?.prompt || ''
      const instruction = [agentPrompt, systemInstructions.trim(), workspaceContext ? `Local workspace files:\n${workspaceContext.content}` : ''].filter(Boolean).join('\n\n')
      const payloadMessages = base.filter(m => m.role !== 'assistant' || textOf(m).trim()).map(m => ({ role: m.role, content: requestContent(m, undefined, t('describeImage')) }))
      if (instruction) payloadMessages.unshift({ role: 'system', content: instruction })
      const response = await fetch(`${GW}/v1/chat/completions`, {
        method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }), signal: controller.signal,
        body: JSON.stringify({ model: selectedModel, messages: payloadMessages, max_tokens: 2048, temperature, top_p: topP, stream: true }),
      })
      armTimeout()
      if (!response.ok) {
        if (response.status === 401) throw new Error(t('errorUnauthorized'))
        const responseText = await response.text()
        let data
        try { data = JSON.parse(responseText) } catch { data = null }
        throw new Error(data?.error ? errorText(data.error, t) : typeof data?.detail === 'string' ? data.detail : data?.message || t('errorHttp', { status: response.status }))
      }
      if (!response.body) throw new Error(t('errorNoBody'))
      if (!response.headers.get('content-type')?.includes('text/event-stream')) {
        const text = await response.text()
        let json
        try { json = JSON.parse(text) } catch { json = null }
        throw new Error(json?.error ? errorText(json.error, t) : t('errorNoSse'))
      }
      reader = response.body.getReader()
      const decoder = new TextDecoder()
      if (mounted.current) { setStatus('streaming'); setConnection('online') }
      while (!completed) {
        const { done, value } = await reader.read()
        if (done) { buffer += decoder.decode(); consumeBuffer(true); break }
        armTimeout()
        buffer += decoder.decode(value, { stream: true })
        buffer = buffer.replace(/\r\n/g, '\n')
        consumeBuffer()
      }
      if (!completed) throw new Error(t('errorStreamEnded'))
      if (!content.trim()) throw new Error(reasoning.trim() ? t('errorReasoningOnly') : t('errorEmpty'))
      patch({ streaming: false, incomplete: false, error: null })
      playSound('done')
    } catch (error) {
      const message = controller.signal.aborted ? (abortReason.current === 'user' ? t('errorStopped') : abortReason.current === 'timeout' ? t('errorTimeout') : t('errorBroken')) : error.message || t('errorGateway')
      if (abortReason.current !== 'user') playSound('error')
      patch({ streaming: false, incomplete: true, error: message })
    } finally {
      clearTimeout(inactivityTimer)
      if (reader) { try { await reader.cancel() } catch { /* Already closed by abort. */ } }
      streamController.current = null
      sendLock.current = false
      if (mounted.current) {
        setStatus('idle')
        setPollRevision(r => r + 1)
        // Return the caret to the composer, unless the user moved to another field.
        const active = document.activeElement
        const elsewhere = active && active !== document.body && active !== inputRef.current
          && !(typeof active.closest === 'function' && active.closest('.composer'))
        if (!elsewhere) inputRef.current?.focus()
      }
    }
  }
  function stopStream() { abortReason.current = 'user'; streamController.current?.abort() }
  function startConversation() {
    if (sendLock.current) return
    cancelSpeech()
    recognition.current?.abort()
    const next = newConversation(t)
    setConversations(previous => [next, ...previous])
    setActiveId(next.id)
    setInput(''); setAttachments([]); setSearch(''); setEditingId(null)
    if (window.matchMedia('(max-width: 900px)').matches) setSidebarOpen(false)
    inputRef.current?.focus()
  }
  function selectConversation(id) {
    if (sendLock.current) return
    cancelSpeech()
    recognition.current?.abort()
    setActiveId(id); setInput(''); setAttachments([]); setSearch(''); setEditingId(null); setRenamingId(null)
    if (window.matchMedia('(max-width: 900px)').matches) setSidebarOpen(false)
  }
  function startRename(conversation) {
    setRenamingId(conversation.id)
    setRenameText(conversation.title)
    setEditingId(null)
  }
  function commitRename(id) {
    const title = renameText.trim()
    setRenamingId(null)
    if (!title) return
    setConversations(list => list.map(c => c.id === id ? { ...c, title } : c))
    notify(t('chatRenamed'))
  }
  function togglePin(id) {
    const target = conversations.find(c => c.id === id)
    setConversations(list => list.map(c => c.id === id ? { ...c, pinned: !c.pinned } : c))
    notify(t(target?.pinned ? 'chatUnpinned' : 'chatPinned'))
  }
  function deleteConversation(id) {
    if (sendLock.current) return
    const target = conversations.find(c => c.id === id)
    if (!target || !window.confirm(t('confirmDeleteChatNamed', { title: target.title }))) return
    cancelSpeech()
    recognition.current?.abort()
    setRenamingId(null)
    const remaining = conversations.filter(c => c.id !== id)
    if (!remaining.length) {
      const next = newConversation(t)
      setConversations([next])
      setActiveId(next.id)
    } else {
      setConversations(remaining)
      if (id === conversationId) {
        const next = conversationOrder(remaining)[0]
        setActiveId(next.id)
        setInput(''); setAttachments([]); setSearch(''); setEditingId(null)
      }
    }
    notify(t('chatDeleted'))
  }
  function regenerate(index) {
    if (sendLock.current || index < 1) return
    const base = messages.slice(0, index)
    if (index < messages.length - 1 && !window.confirm(t('confirmRegenerate'))) return
    send(base)
  }
  function resendEdit(index) {
    if (sendLock.current) return
    if (!editText.trim() && !messages[index].attachments?.length) return
    if (index < messages.length - 1 && !window.confirm(t('confirmEdit'))) return
    const updated = { ...messages[index], content: editText.trim() }
    if (!updated.attachments?.length) updated.requestContent = requestContent(updated, editText.trim(), t('describeImage'))
    send([...messages.slice(0, index), updated])
  }
  function exportConversation(format = 'json') {
    if (format === 'json') download(JSON.stringify({ app: 'ProxyPal', exportedAt: new Date().toISOString(), conversation }, null, 2), 'proxypal-conversation.json', 'application/json')
    else download(messages.map(m => `## ${m.role === 'user' ? t('you') : t('assistant')}${m.incomplete ? ` · ${t('incomplete')}` : ''}\n\n${textOf(m)}${m.attachments?.length ? '\n\n' + m.attachments.map(a => `[${t('attach')}: ${a.name}]${a.kind === 'text' ? '\n' + a.text : ''}`).join('\n\n') : ''}${m.error ? '\n\n> ' + m.error : ''}`).join('\n\n---\n\n'), 'proxypal-conversation.md', 'text/markdown;charset=utf-8')
  }
  async function mutatePool(path, method, body, successText) {
    if (poolPending) return false
    setPoolPending(true)
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 12000)
    try {
      const response = await fetch(`${GW}${path}`, { method, signal: controller.signal, headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify(body) })
      if (!response.ok) throw new Error('Pool operation failed')
      const text = await response.text()
      let data = null
      if (text) { try { data = JSON.parse(text); applyStatus(data) } catch { /* A refresh retrieves the safe status. */ } }
      setPollRevision(r => r + 1)
      let message = successText || (path.endsWith('/reset') ? t('resetDone') : t('poolSaved'))
      let error = false
      if (data?.validation) {
        const { added = 0, rejected = 0, unverified = 0 } = data.validation
        if (added === 0 && rejected > 0) { message = t('keysRejectedCount', { count: rejected }); error = true }
        else if (added === 0) message = t('keysDuplicate')
        else {
          message = t('keysValidated', { added, rejected })
          if (unverified) message += ` · ${t('keysUnverified', { count: unverified })}`
          error = rejected > 0
        }
      }
      notify(message, error)
      return data || true
    } catch {
      // Never display mutation response bodies: they may echo a submitted secret.
      notify(t('poolUnconfirmed'), true)
      setPollRevision(r => r + 1)
      return false
    } finally { clearTimeout(timeout); if (mounted.current) setPoolPending(false) }
  }
  async function addKeys(event) {
    event.preventDefault()
    const apiKeys = [...new Set(keyInput.split(/[\s,;]+/).map(k => k.trim()).filter(Boolean))]
    if (!apiKeys.length) { notify(t('errorEnterKey'), true); return }
    if (!Number.isInteger(Number(tokenBudget)) || tokenBudget < 1 || !Number.isInteger(Number(requestBudget)) || requestBudget < 1) { notify(t('errorBudgets'), true); return }
    const body = { provider: providerIds.includes(provider) ? provider : 'groq', api_keys: apiKeys, label: keyLabel.trim() || undefined, token_budget: Number(tokenBudget), request_budget: Number(requestBudget) }
    const data = await mutatePool('/pool/keys', 'POST', body)
    if (data) { setKeyInput(''); setShowKeys(false) }
  }
  async function addProvider(event) {
    event.preventDefault()
    const name = providerName.trim().toLowerCase()
    const baseUrl = providerUrl.trim()
    const models = [...new Set(providerModels.split(/[\s,;]+/).map(item => item.trim()).filter(Boolean))]
    if (!/^[a-z0-9][a-z0-9_-]{1,31}$/.test(name) || !/^https?:\/\/\S+$/i.test(baseUrl) || !models.length) {
      notify(t('providerInvalid'), true)
      return
    }
    const data = await mutatePool('/pool/providers', 'POST', { name, base_url: baseUrl, models }, t('providerAdded'))
    if (data) { setProvider(name); setProviderName(''); setProviderUrl(''); setProviderModels('') }
  }
  async function removeProvider(name) {
    if (!window.confirm(t('confirmDeleteProvider', { name }))) return
    const data = await mutatePool(`/pool/providers/${encodeURIComponent(name)}`, 'DELETE', undefined, t('providerDeleted'))
    if (data && provider === name) setProvider('groq')
  }
  async function saveProviderModels(item, models, message) {
    return !!(await mutatePool(`/pool/providers/${encodeURIComponent(item.provider)}/models`, 'PATCH', { models }, message))
  }
  function dropModel(item, model) {
    saveProviderModels(item, item.models.filter(entry => entry !== model), t('modelRemoved'))
  }
  async function addModel(item) {
    const value = (modelDraft[item.provider] || '').trim()
    if (!value) { notify(t('errorEnterModel'), true); return }
    if (item.models.includes(value)) { notify(t('modelAlready'), true); return }
    if (await saveProviderModels(item, [...item.models, value], t('modelAdded')))
      setModelDraft(drafts => ({ ...drafts, [item.provider]: '' }))
  }
  function closeSettings() { setSettings(null); setKeyInput(''); setShowKeys(false) }
  async function loadWorkspace(event) {
    event.preventDefault()
    if (!preferences.workspacePath.trim() || workspaceLoading) return
    setWorkspaceLoading(true)
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 15000)
    try {
      const response = await fetch(`${GW}/workspace/snapshot`, { method: 'POST', signal: controller.signal, headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify({ path: preferences.workspacePath.trim() }) })
      if (!response.ok) {
        const failure = await response.json().catch(() => null)
        const detail = typeof failure?.detail === 'string' ? failure.detail : ''
        notify(detail.includes('WORKSPACE_ROOT') ? t('workspaceOutsideRoot') : detail.includes('Not a directory') ? t('workspaceMissing') : t('workspaceLoadFail'), true)
        return
      }
      const data = await response.json()
      if (data.error || !Array.isArray(data.files)) throw new Error('Invalid snapshot')
      if (!data.files.length) { notify(t('workspaceEmpty'), true); setWorkspaceContext(null); return }
      setWorkspaceContext({ name: preferences.workspacePath.split(/[\\/]/).filter(Boolean).pop(), count: data.files.length, content: data.files.map(f => `### ${f.path}\n${f.content}`).join('\n\n') })
      notify(t('workspaceLoaded', { count: data.files.length }))
    } catch { notify(t('workspaceLoadFail'), true) }
    finally { clearTimeout(timeout); if (mounted.current) setWorkspaceLoading(false) }
  }

  const visibleMessages = messages.map((message, index) => ({ message, index })).filter(({ message }) => !search.trim() || [textOf(message), message.reasoning || '', ...(message.attachments || []).map(a => a.name)].join(' ').toLowerCase().includes(search.trim().toLowerCase()))
  const connectionLabel = !online ? t('noNetwork') : connection === 'online' ? t('gatewayConnected') : connection === 'connecting' ? t('gatewayConnecting') : t('gatewayDisconnected')
  const showSidebar = sidebarOpen && !focusMode
  const statusLabel = status === 'thinking' ? t('thinking') : status === 'streaming' ? t('typing') : t('ready')
  const voicesForLanguage = voices.filter(voice => voiceLang === 'auto' || voice.lang.toLowerCase().startsWith(SPEECH_CODES[voiceLang].split('-')[0]))
  function providerChip(id, label) {
    return <button type="button" key={id} className={`provider-chip ${provider === id ? 'selected' : ''}`} aria-pressed={provider === id} disabled={poolPending} onClick={() => setProvider(id)} title={label}>
      <ProviderMark id={id} />
      <span dir="auto">{label}</span>
      {provider === id && <Icon name="check" size={12} />}
    </button>
  }

  return <div className={`app-shell ${showSidebar ? 'with-sidebar' : ''}`}>
    {splash && <div className={`splash ${splashLeaving ? 'is-leaving' : ''}`} role="status" aria-label={t('splashLoading')}>
      <span className="splash-halo" aria-hidden="true" />
      <span className="splash-mark"><Logo size={68} /></span>
      <span className="splash-word">ProxyPal<span className="brand-dot">.</span></span>
      <span className="splash-caption">{t('tagline')}</span>
      <span className="splash-bar" aria-hidden="true"><i /></span>
    </div>}
    <a className="skip-link" href="#composer">{t('skipToComposer')}</a>
    {showSidebar && <button className="sidebar-scrim" aria-label={t('closeMenu')} onClick={() => setSidebarOpen(false)} />}
    <aside className={`sidebar ${showSidebar ? 'is-open' : ''}`} aria-label={t('conversationHistory')} inert={!showSidebar}>
      <div className="brand"><span className="brand-symbol"><Logo size={25} /></span><div><strong>ProxyPal<span className="brand-dot">.</span></strong><span className="brand-caption">{t('tagline')}</span></div><IconButton icon="sidebar" label={t('hideMenu')} onClick={() => setSidebarOpen(false)} /></div>
      <button className="new-chat button" onClick={startConversation} disabled={busy}><Icon name="plus" /><span>{t('newChat')}</span><kbd>↵</kbd></button>
      <div className="sidebar-section-label"><span>{t('yourSpace')}</span><span>{conversations.length}</span></div>
      <nav className="conversation-list" aria-label={t('conversationHistory')}>{conversationOrder(conversations).map(c => <div key={c.id} className={`conversation-row${c.id === conversationId ? ' selected' : ''}${c.pinned ? ' pinned' : ''}`}>
        {renamingId === c.id ? <form className="rename-form" onSubmit={e => { e.preventDefault(); commitRename(c.id) }}>
          <input autoFocus aria-label={t('renameChat')} value={renameText} maxLength={80} dir="auto" onChange={e => setRenameText(e.target.value)} onKeyDown={e => { if (e.key === 'Escape') { e.preventDefault(); setRenamingId(null) } }} />
          <IconButton icon="check" className="rename-action" label={t('saveName')} type="submit" />
          <IconButton icon="close" className="rename-action" label={t('cancel')} onClick={() => setRenamingId(null)} />
        </form> : <>
          <button className="conversation-link" disabled={busy} aria-current={c.id === conversationId ? 'page' : undefined} onClick={() => selectConversation(c.id)}><Icon name={c.pinned ? 'pin' : 'chat'} size={16} /><span dir="auto">{c.title}</span>{c.id === conversationId && <span className="current-mark" />}</button>
          <IconButton icon="pen" className="conversation-delete" label={t('renameChatNamed', { title: c.title })} disabled={busy} onClick={() => startRename(c)} />
          <IconButton icon="pin" className={`conversation-delete conversation-pin ${c.pinned ? 'is-pinned' : ''}`} label={c.pinned ? t('unpinChat') : t('pinChat')} disabled={busy} onClick={() => togglePin(c.id)} />
          <IconButton icon="trash" className="conversation-delete" label={t('deleteChatNamed', { title: c.title })} disabled={busy} onClick={() => deleteConversation(c.id)} />
        </>}
      </div>)}</nav>
      <div className="sidebar-bottom"><PoolCard pool={pool} connection={online ? connection : 'offline'} onSettings={() => setSettings('pool')} t={t} locale={locale} /><div className="profile"><Avatar id={avatar} name={displayName} /><div><strong dir="auto">{displayName}</strong><small>{t('savedOnDevice')}</small></div><IconButton icon="settings" label={t('settings')} onClick={() => setSettings('general')} /></div></div>
    </aside>

    <main className="main-panel">
      <header className="topbar"><div className="topbar-leading">{!showSidebar && <IconButton icon="sidebar" label={t('showMenu')} onClick={() => { setFocusMode(false); setSidebarOpen(true) }} />}<div className="workspace-heading"><span className="eyebrow">{t('workspace')}</span><strong>{t('workspaceTitle')}</strong></div><span className="header-divider" /><ModelPicker providers={providers} pool={pool} value={selectedModel} onChange={value => pref('selectedModel', value)} disabled={busy} modelHealth={modelHealth} testingModel={testingModel} onUpdate={updateModels} updating={modelsUpdating} t={t} /></div>
        <div className="topbar-actions"><IconButton icon={mascot === 'hidden' ? 'eye' : mascot} label={mascot === 'hidden' ? t('showCompanion') : t('hideCompanion')} aria-pressed={mascot !== 'hidden'} onClick={() => pref('mascot', mascot === 'hidden' ? lastMascot.current : 'hidden')} /><IconButton icon={audioEnabled ? 'audio' : 'muted'} label={audioEnabled ? t('disableAudio') : t('enableAudio')} aria-pressed={audioEnabled} onClick={toggleAudio} /><IconButton icon={darkThemes.has(theme) ? 'sun' : 'moon'} label={darkThemes.has(theme) ? t('switchToLight') : t('switchToDark')} onClick={() => pref('theme', darkThemes.has(theme) ? 'light' : 'dark')} /><IconButton icon="focus" className="focus-toggle" label={focusMode ? t('showMenu') : t('hideMenu')} aria-pressed={focusMode} onClick={() => setFocusMode(v => !v)} /><IconButton icon="settings" label={t('settings')} className="mobile-settings" onClick={() => setSettings('general')} /></div>
      </header>
      <div className="conversation-toolbar"><div className="chat-breadcrumb"><Icon name="chat" size={15} /><span dir="auto">{conversation.title}</span></div><div className="toolbar-end"><label className="search-box"><Icon name="search" size={15} /><input aria-label={t('searchMessages')} placeholder={t('searchMessages')} value={search} dir="auto" onChange={e => setSearch(e.target.value)} />{search && <IconButton icon="close" label={t('clearSearch')} onClick={() => setSearch('')} />}</label><IconButton icon="download" label={t('exportConversation')} onClick={() => exportConversation()} /><span className="connection-label" role="status" aria-label={connectionLabel} title={connectionLabel}><span className={`connection-dot ${connection === 'online' && online ? 'connected' : ''}`} /><span>{connection === 'online' && online ? t('connected') : t('disconnected')}</span></span></div></div>
      {connection !== 'online' && <div className="offline-banner" role="status"><Icon name="info" size={14} />{t('offlineBanner', { message: connectionLabel })}</div>}
      {connection === 'online' && staleGateway && <div className="offline-banner stale-banner" role="alert"><Icon name="info" size={14} />{t('staleGateway')}</div>}
      {storageWarning && <div className="offline-banner" role="alert">{t('storageWarning')}</div>}
      <div className="chat-scroll" ref={chatRef} onScroll={e => { const el = e.currentTarget; nearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 140 }}>
        {!messages.length ? <section className="welcome"><div className="welcome-kicker"><span className="mini-line" /> {t('welcomeKicker')}</div><div className="welcome-title"><h1>{t('welcomeTitle')}</h1>{mascot !== 'hidden' && <span className={`mascot mascot-${mascot}`} title={t('companion')}><Mascot shape={mascot} mood={pool.keys.length ? 'idle' : 'sleepy'} size={52} /></span>}</div><p className="welcome-description">{t('welcomeDescription').split('\n').map((line, index) => index ? <span key={line}><br />{line}</span> : line)}</p><div className="prompt-grid">{PROMPTS.map(p => <button className="prompt-card" key={p.titleKey} onClick={() => { setInput(t(p.textKey)); inputRef.current?.focus() }}><span className="prompt-icon"><Icon name={p.icon} size={20} /></span><strong>{t(p.titleKey)}</strong><span>{t(p.hintKey)}</span><Icon className="prompt-arrow" name="plus" size={16} /></button>)}</div><div className="welcome-footnote"><Icon name="key" size={14} /><span>{t('welcomeFootnote')}</span></div>{!pool.keys.length && <button className="button primary welcome-key" onClick={() => setSettings('pool')}><Icon name="key" size={16} />{t('addFirstKey')}</button>}</section> : <div className="message-list">
          {search.trim() && <p className="search-results" role="status">{visibleMessages.length ? t('searchResultCount', { count: visibleMessages.length }) : t('noSearchResults')}</p>}
          {visibleMessages.map(({ message: m, index }) => <article className={`message ${m.role === 'user' ? 'user-message' : 'assistant-message'}`} key={m.id || index} aria-label={m.role === 'user' ? t('yourMessage') : t('assistantReply')}>
            <div className="message-avatar">{m.role === 'user' ? <Avatar id={avatar} name={displayName} className="message-avatar-image" /> : <Icon name={mascot === 'hidden' ? 'chat' : mascot} size={20} />}</div><div className="message-body"><div className="message-meta"><strong>{m.role === 'user' ? t('you') : t('assistant')}</strong>{m.role === 'assistant' && <><bdi className="message-model">{m.model}</bdi>{m.gateway?.label && <span className="gateway-label" title={`${m.gateway.provider || '—'}${m.gateway.switched ? ` · ${t('companionSwitched')}` : ''}`} dir="auto">{m.gateway.label}</span>}</>}{m.streaming && <span className="stream-label">{statusLabel}</span>}{m.context?.trimmed > 0 && <span className="state-tag context-tag" title={t('contextTrimmedHint', { count: m.context.trimmed, limit: number(m.context.limit) })}>{t('contextTrimmed')}</span>}{m.context?.truncated && <span className="state-tag context-tag" title={t('contextTruncatedHint')}>{t('contextTruncated')}</span>}{m.substituted && <span className="state-tag substituted-tag" title={t('modelSubstitutedHint', { from: m.substituted, to: m.model })}>{t('modelSubstituted')}</span>}{m.incomplete && <span className="state-tag incomplete-tag">{t('incomplete')}</span>}</div>
              {m.attachments?.length > 0 && <div className="message-attachments">{m.attachments.map(a => a.kind === 'image' ? <figure key={a.id}><img src={a.url} alt={a.name} loading="lazy" /><figcaption dir="auto">{a.name}</figcaption></figure> : <span className="attachment-chip" key={a.id}><Icon name="file" size={15} /><span dir="auto">{a.name}</span></span>)}</div>}
              {editingId === m.id ? <div className="inline-edit"><textarea aria-label={t('editMessage')} value={editText} onChange={e => setEditText(e.target.value)} rows={4} dir="auto" /><p className="muted">{t('editNotice')}</p><div className="button-row"><button className="button primary" disabled={busy || readingFiles || (!editText.trim() && !m.attachments?.length)} onClick={() => resendEdit(index)}>{t('saveChanges')}</button><button className="button subtle" onClick={() => setEditingId(null)}>{t('cancel')}</button></div></div> : <>
                {m.reasoning && <details className="reasoning"><summary><Icon name="spark" size={14} /> {t('reasoning')}</summary><div dir="auto">{m.reasoning}</div></details>}
                <div className="message-content" dir="auto">{m.streaming && !textOf(m) ? <div className="stream-placeholder" role="status"><span className="typing-dot" />{statusLabel}…</div> : <Markdown text={textOf(m)} onCopy={copy} onPreview={code => { setCodePreview(code); setPreviewTab('preview') }} t={t} />}</div>
                {m.error && <div className="message-error" role="alert" dir="auto"><Icon name="info" size={16} /><span>{m.error}</span></div>}
                {!m.streaming && <div className="message-actions"><button className="text-button" onClick={() => copy(textOf(m))} disabled={!textOf(m)} title={t('copy')}><Icon name="copy" size={14} />{t('copy')}</button>{m.role === 'user' ? <button className="text-button" disabled={busy || readingFiles} onClick={() => { setEditingId(m.id); setEditText(textOf(m)) }}><Icon name="pen" size={14} />{t('edit')}</button> : <><button className="text-button" disabled={busy || readingFiles} onClick={() => regenerate(index)}><Icon name="refresh" size={14} />{t('regenerate')}</button><button className="text-button" disabled={!audioEnabled || !textOf(m)} title={audioEnabled ? t('readHint') : t('audioDisabledHint')} onClick={() => readResponse(m)}><Icon name={speakingId === m.id ? 'stop' : 'audio'} size={14} />{speakingId === m.id ? t('stopReading') : t('read')}</button>{m.usage?.total_tokens != null && <bdi className="usage-label">{number(m.usage.total_tokens)} tokens</bdi>}</>}</div>}
              </>}
            </div>
          </article>)}
        </div>}
      </div>
      <footer className="composer-area"><div className="composer-wrap">{workspaceContext && <div className="context-pill"><Icon name="file" size={14} /><span dir="auto">{t('contextFiles', { name: workspaceContext.name, count: workspaceContext.count })}</span><IconButton icon="close" label={t('removeCurrentContext')} disabled={busy} onClick={() => setWorkspaceContext(null)} /></div>}
        {attachments.length > 0 && <div className="pending-attachments">{attachments.map(a => <div className="pending-attachment" key={a.id}>{a.kind === 'image' ? <img src={a.url} alt="" /> : <Icon name="file" size={18} />}<span dir="auto">{a.name}</span><IconButton icon="close" label={t('removeAttachment', { name: a.name })} disabled={busy} onClick={() => setAttachments(previous => previous.filter(item => item.id !== a.id))} /></div>)}</div>}
        <form className={`composer ${busy ? 'is-busy' : ''}`} onSubmit={e => { e.preventDefault(); send() }}><textarea id="composer" ref={inputRef} aria-label={t('composerLabel')} placeholder={t('composerPlaceholder')} dir="auto" rows={2} value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send() } }} /><div className="composer-bottom"><div className="composer-tools"><IconButton icon="attach" label={t('attachmentLabel')} disabled={busy || readingFiles} onClick={() => fileRef.current?.click()} /><input ref={fileRef} type="file" multiple accept="image/*,text/*,.js,.jsx,.ts,.tsx,.py,.json,.md,.csv,.html,.css,.xml,.yaml,.yml,.sql,.sh,.log" className="visually-hidden" tabIndex={-1} onChange={attachFiles} /><IconButton icon={listening ? 'stop' : 'mic'} label={listening ? t('dictationStop') : t('dictation')} aria-pressed={listening} disabled={busy} onClick={toggleVoice} /><span className="tool-divider" /><select aria-label={t('agentSelect')} className="agent-select" value={agent} disabled={busy} onChange={e => pref('agent', e.target.value)}>{AGENTS.map(item => <option key={item.id} value={item.id}>{t(item.labelKey)}</option>)}</select></div><div className="composer-send"><span className="composer-state" role="status">{readingFiles ? t('readingFiles') : listening ? t('micOn') : busy ? statusLabel : audioEnabled ? t('audioManual') : t('audioOffShort')}</span>{busy ? <button key="stop" type="button" className="send-button stop-button" onClick={event => { event.preventDefault(); stopStream() }} aria-label={t('stopReply')} title={t('stopReplyTitle')}><Icon name="stop" size={17} /></button> : <button key="send" className="send-button" type="submit" disabled={readingFiles || !selectedModel || (!input.trim() && !attachments.length)} aria-label={t('sendMessage')} title={t('sendHint')}><Icon name="send" size={19} /></button>}</div></div></form>
        <div className="composer-caption"><span>{t('enterHint')}</span>{mascot !== 'hidden' && <Companion pool={pool} shape={mascot} status={status} switched={switchedRecently} onHide={() => pref('mascot', 'hidden')} t={t} />}<span>{t('disclaimer')}</span></div>
      </div></footer>
    </main>

    {settings && <Dialog title={t('settingsTitle')} onClose={closeSettings} className="settings-dialog" t={t}><div className="settings-tabs"><button className={settings === 'general' ? 'active' : ''} aria-pressed={settings === 'general'} onClick={() => setSettings('general')}><Icon name="settings" size={16} />{t('generalTab')}</button><button className={settings === 'pool' ? 'active' : ''} aria-pressed={settings === 'pool'} onClick={() => setSettings('pool')}><Icon name="key" size={16} />{t('poolTab')} <span>{pool.keys.length}</span></button></div><div className="dialog-content">
      {settings === 'general' ? <>
        <section className="settings-section"><div className="section-heading"><h3>{t('displaySection')}</h3><Icon name="spark" size={18} /></div>
          <div className="field">{t('language')}<span className="segmented">{Object.entries(locales).map(([id, info]) => <button type="button" key={id} className={locale === id ? 'active' : ''} aria-pressed={locale === id} onClick={() => pref('locale', id)}><Icon name="globe" size={14} />{info.label}</button>)}</span><small className="field-hint">{t('languageHint')}</small></div>
          <div className="field">{t('theme')}<div className="theme-grid">{themes.map(id => <button type="button" key={id} className={`theme-choice ${theme === id ? 'selected' : ''}`} aria-pressed={theme === id} onClick={() => pref('theme', id)}><span className="theme-preview" style={{ background: THEME_PREVIEW[id].bg, borderColor: THEME_PREVIEW[id].border }}><i style={{ background: THEME_PREVIEW[id].surface }} /><i style={{ background: THEME_PREVIEW[id].accent }} /></span><span>{t(`theme_${id}`)}</span></button>)}</div></div>
          <div className="field">{t('font')}<div className="font-grid">{fonts.map(item => <button type="button" key={item.id} className={`font-choice ${font === item.id ? 'selected' : ''}`} aria-pressed={font === item.id} onClick={() => pref('font', item.id)}><span className="font-sample" style={{ fontFamily: item.family }}>فكرة واضحة 123</span><small>{item.label}</small></button>)}</div><small className="field-hint">{t('fontHint')}</small></div>
          <label className="field">{t('displayName')}<input value={userName} onChange={e => pref('userName', e.target.value)} maxLength={80} dir="auto" placeholder={t('defaultUserName')} /></label>
          <div className="field">{t('avatarSection')}<div className="avatar-grid">{['initial', ...AVATARS].map(id => <button type="button" key={id} className={`avatar-choice ${avatar === id ? 'selected' : ''}`} aria-pressed={avatar === id} aria-label={t(`avatar_${id}`)} onClick={() => pref('avatar', id)}>{id === 'initial' ? <span className="avatar-choice-initial">{displayName.trim().charAt(0) || 'P'}</span> : <img src={AVATAR_SRC[id]} alt="" />}<span>{t(`avatar_${id}`)}</span></button>)}</div></div>
          <div className="field">{t('companion')}<div className="mascot-grid">{['orb', 'robot', 'cat', 'hidden'].map(id => <button type="button" key={id} className={`mascot-choice ${mascot === id ? 'selected' : ''}`} aria-pressed={mascot === id} onClick={() => pref('mascot', id)}>{id === 'hidden' ? <Icon name="eye" size={20} /> : <Mascot shape={id} mood={mascot === id ? 'happy' : 'idle'} size={30} />}<span>{t(`companion_${id}`)}</span></button>)}</div></div>
          <div className="setting-toggle"><div><strong>{t('audio')} · {audioEnabled ? t('audioOn') : t('audioOff')}</strong><p>{t('audioDesc')}</p></div><button className="button subtle" aria-pressed={audioEnabled} onClick={toggleAudio}><Icon name={audioEnabled ? 'audio' : 'muted'} size={16} />{audioEnabled ? t('disable') : t('enable')}</button></div>
          <div className="setting-toggle"><div><strong>{t('soundEffects')} · {sound ? t('soundOn') : t('soundOff')}</strong><p>{t('soundDesc')}</p></div><button className="button subtle" aria-pressed={sound} onClick={() => pref('sound', !sound)}><Icon name={sound ? 'wave' : 'muted'} size={16} />{sound ? t('disable') : t('enable')}</button></div>
          <div className="voice-box">
            <div className="section-heading"><h4><Icon name="wave" size={16} /> {t('voiceSection')}</h4></div>
            <p className="muted">{t('voiceHint')}</p>
            <div className="form-grid">
              <label className="field">{t('voiceLanguage')}<select value={voiceLang} onChange={e => pref('voiceLang', e.target.value)}><option value="auto">{t('voiceLang_auto')}</option><option value="ar">{t('voiceLang_ar')}</option><option value="en">{t('voiceLang_en')}</option><option value="fr">{t('voiceLang_fr')}</option></select></label>
              <label className="field">{t('voice')}<select value={voiceURI} onChange={e => pref('voiceURI', e.target.value)}><option value="">{t('voiceDefault')}</option>{voicesForLanguage.map(voice => <option key={voice.voiceURI} value={voice.voiceURI}>{voice.name} · {voice.lang}</option>)}</select></label>
            </div>
            <div className="form-grid"><label className="field">{t('voiceRate')} · {voiceRate.toFixed(2)}<input type="range" min="0.6" max="1.5" step="0.05" value={voiceRate} onChange={e => pref('voiceRate', Number(e.target.value))} /></label><label className="field">{t('voicePitch')} · {voicePitch.toFixed(2)}<input type="range" min="0.7" max="1.3" step="0.05" value={voicePitch} onChange={e => pref('voicePitch', Number(e.target.value))} /></label></div>
            <button className="button subtle" type="button" onClick={testVoice}><Icon name="audio" size={16} />{t('testVoice')}</button>
          </div>
        </section>
        <section className="settings-section"><h3>{t('responseSection')}</h3><label className="field">{t('systemInstructions')}<textarea value={systemInstructions} disabled={busy} onChange={e => pref('systemInstructions', e.target.value)} rows={4} dir="auto" placeholder={t('systemPlaceholder')} /></label><div className="form-grid"><label className="field">Temperature · {temperature.toFixed(2)}<input type="range" min="0" max="2" step="0.05" value={temperature} disabled={busy} onChange={e => pref('temperature', Number(e.target.value))} /></label><label className="field">Top P · {topP.toFixed(2)}<input type="range" min="0.05" max="1" step="0.05" value={topP} disabled={busy} onChange={e => pref('topP', Number(e.target.value))} /></label></div></section>
        <details className="settings-section settings-fold"><summary><span className="fold-title"><Icon name="file" size={15} /><h3>{t('workspaceSection')}</h3></span><span className="fold-meta">{workspaceContext ? `${workspaceContext.name} · ${workspaceContext.count}` : t('optional')}<Icon name="chevron" size={15} /></span></summary><div className="fold-body"><p className="muted">{t('workspaceNote')}</p>{workspaceRoot && <p className="fold-root"><Icon name="globe" size={13} /><bdi>{t('workspaceRootHint', { root: workspaceRoot })}</bdi></p>}<form onSubmit={loadWorkspace}><label className="field">{t('workspacePath')}<input dir="ltr" value={preferences.workspacePath} disabled={busy || workspaceLoading} onChange={e => pref('workspacePath', e.target.value)} placeholder={workspaceRoot || 'C:/projects/my-app'} spellCheck={false} /></label><button className="button subtle" disabled={busy || workspaceLoading || !preferences.workspacePath.trim()}><Icon name="file" size={16} />{workspaceLoading ? t('loading') : t('loadContext')}</button></form>{workspaceContext && <button className="text-button" disabled={busy} onClick={() => setWorkspaceContext(null)}>{t('removeContext')}</button>}</div></details>
        <section className="settings-section"><h3>{t('privacySection')}</h3><p className="muted">{t('privacyNote')}</p><div className="button-row"><button className="button subtle" onClick={() => exportConversation('json')}><Icon name="download" size={16} />{t('exportJson')}</button><button className="button subtle" onClick={() => exportConversation('markdown')}>{t('exportMarkdown')}</button><button className="text-button" disabled={busy} onClick={() => { if (window.confirm(t('confirmDelete'))) { const remaining = conversations.filter(c => c.id !== conversationId); const next = remaining.length ? remaining : [newConversation(t)]; setConversations(next); setActiveId(next[0].id); setInput(''); setAttachments([]); setSearch(''); setEditingId(null); cancelSpeech() } }}><Icon name="trash" size={15} />{t('deleteConversation')}</button></div></section>
      </> : <>
        <section className="settings-section"><div className="section-heading"><h3>{t('routingSection')}</h3><Icon name="layers" size={18} /></div><p className="muted">{t('routingHint')}</p><div className="strategy-grid">{['sticky', 'round_robin', 'least_used'].map(id => <button type="button" key={id} className={`strategy-choice ${(pool.strategy || 'sticky') === id ? 'selected' : ''}`} aria-pressed={(pool.strategy || 'sticky') === id} disabled={poolPending} onClick={() => mutatePool('/settings', 'PATCH', { strategy: id }, t('strategySaved'))}><strong>{t(`strategy_${id}`)}</strong><small>{t(`strategyDesc_${id}`)}</small></button>)}</div></section>
        <section className="settings-section"><div className="section-heading"><h3>{t('groupKeys')}</h3><span className="state-tag">{t('keysCount', { count: pool.keys.length })}</span></div><p className="budget-explanation"><Icon name="info" size={17} /><span>{t('budgetsExplained')}</span></p>{pool.keys.length ? <div className="existing-key-list">{pool.keys.map(item => <KeyEditor key={item.id} item={item} pending={poolPending} onMutation={mutatePool} t={t} locale={locale} />)}</div> : <p className="empty-hint">{t('noKeysYet')}</p>}</section>
        <section className="settings-section"><h3>{t('addKeysTitle')}</h3><p className="muted">{t('addKeysHint')}</p><form onSubmit={addKeys} autoComplete="off"><div className="field provider-field"><span className="field-label">{t('provider')}</span><div className="provider-catalog"><div className="provider-grid">{PROVIDER_CATALOG.slice(0, POPULAR_PROVIDERS).map(item => providerChip(item.id, item.name))}{customProviders.map(item => providerChip(item.provider, item.provider))}</div><button type="button" className="provider-more" aria-expanded={showAllProviders} onClick={() => setShowAllProviders(v => !v)}><Icon name={showAllProviders ? 'chevronUp' : 'chevron'} size={14} /><span>{showAllProviders ? t('showFewerProviders') : t('showAllProviders', { count: PROVIDER_CATALOG.length + customProviders.length })}</span></button>{showAllProviders && <div className="provider-grid provider-grid-all">{PROVIDER_CATALOG.slice(POPULAR_PROVIDERS).map(item => providerChip(item.id, item.name))}</div>}</div></div><label className="field">{t('optionalName')}<input value={keyLabel} disabled={poolPending} onChange={e => setKeyLabel(e.target.value)} maxLength={80} dir="auto" placeholder={t('nameExample')} /></label><label className="field">{t('apiKeys')}<textarea className={`secret-input ${showKeys ? 'revealed' : ''}`} aria-label={t('apiKeys')} dir="ltr" value={keyInput} disabled={poolPending} onChange={e => setKeyInput(e.target.value)} rows={4} spellCheck={false} autoComplete="off" autoCorrect="off" autoCapitalize="off" data-lpignore="true" placeholder={t('keysPerLine')} /></label><button type="button" className="text-button" aria-pressed={showKeys} onClick={() => setShowKeys(v => !v)}><Icon name="eye" size={15} />{showKeys ? t('hideKeys') : t('showKeys')}</button><div className="form-grid"><label className="field">{t('tokenBudget')}<input type="number" min="1" step="1" required value={tokenBudget} disabled={poolPending} onChange={e => setTokenBudget(e.target.value)} /></label><label className="field">{t('requestBudget')}<input type="number" min="1" step="1" required value={requestBudget} disabled={poolPending} onChange={e => setRequestBudget(e.target.value)} /></label></div><button className="button primary" disabled={poolPending || !keyInput.trim()}><Icon name="plus" size={17} />{poolPending ? t('saving') : t('addToPool')}</button></form></section>
        <section className="settings-section"><h3>{t('customProviderTitle')}</h3><p className="muted">{t('customProviderHint')}</p><form onSubmit={addProvider} autoComplete="off"><div className="form-grid"><label className="field">{t('providerName')}<input value={providerName} disabled={poolPending} onChange={e => setProviderName(e.target.value)} dir="ltr" maxLength={32} placeholder="my-provider" /></label><label className="field">{t('baseUrl')}<input value={providerUrl} disabled={poolPending} onChange={e => setProviderUrl(e.target.value)} dir="ltr" maxLength={300} placeholder="https://api.example.com/v1" /></label></div><label className="field">{t('modelsList')}<input value={providerModels} disabled={poolPending} onChange={e => setProviderModels(e.target.value)} dir="ltr" placeholder="model-a, model-b" /></label><button className="button subtle" disabled={poolPending || !providerName.trim() || !providerUrl.trim() || !providerModels.trim()}><Icon name="plus" size={16} />{t('addProvider')}</button></form></section>
        {(providers || []).length > 0 && <section className="settings-section"><div className="section-heading"><h3>{t('configuredProviders')}</h3><span className="state-tag">{t('keysCount', { count: pool.keys.length })}</span></div><p className="muted">{t('configuredProvidersHint')}</p>
          <div className="provider-manage">{providers.map(item => <div className="provider-row" key={item.provider}>
            <div className="provider-row-top"><span className="provider-row-name"><ProviderMark id={item.provider} size={20} /><bdi dir="ltr">{item.provider}</bdi>{item.custom && <em>{t('customBadge')}</em>}</span><small dir="ltr" className="provider-row-url">{item.base_url}</small><span className="provider-row-keys">{t('keysCount', { count: item.key_count })}</span><button className="text-button danger-text" type="button" disabled={poolPending} onClick={() => removeProvider(item.provider)}><Icon name="trash" size={14} />{t('deleteProvider')}</button></div>
            <div className="model-chips">{(item.models || []).map(model => <span className="model-chip" key={model}><bdi dir="ltr">{model}</bdi><button type="button" aria-label={t('removeModel', { model })} disabled={poolPending} onClick={() => dropModel(item, model)}><Icon name="close" size={12} /></button></span>)}{!(item.models || []).length && <span className="empty-hint">{t('noModelsYet')}</span>}</div>
            <form className="model-add" onSubmit={event => { event.preventDefault(); addModel(item) }} autoComplete="off"><input dir="ltr" value={modelDraft[item.provider] || ''} disabled={poolPending} placeholder={t('modelIdPlaceholder')} aria-label={t('addModel')} maxLength={200} onChange={event => setModelDraft(drafts => ({ ...drafts, [item.provider]: event.target.value }))} /><button type="submit" className="button subtle" disabled={poolPending}><Icon name="plus" size={14} />{t('addModel')}</button></form>
          </div>)}</div></section>}
      </>}
    </div></Dialog>}
    {!splash && !onboarded && <div className="onboarding-layer" role="dialog" aria-modal="true" aria-labelledby="onboarding-title">
      <form className="onboarding-card" onSubmit={completeOnboarding}>
        <span className="onboarding-mark"><Logo size={38} /></span>
        <span className="onboarding-kicker">ProxyPal<span className="brand-dot">.</span></span>
        <h2 id="onboarding-title">{t('onboardingTitle')}</h2>
        <p className="onboarding-hint">{t('onboardingHint')}</p>
        <label className="field">{t('firstName')}<input autoFocus value={onboardName} onChange={e => setOnboardName(e.target.value)} maxLength={40} dir="auto" placeholder={t('firstNamePlaceholder')} /></label>
        <div className="field">{t('chooseAvatar')}<div className="avatar-grid onboarding-avatars">{AVATARS.map(id => <button type="button" key={id} className={`avatar-choice ${onboardAvatar === id ? 'selected' : ''}`} aria-pressed={onboardAvatar === id} aria-label={t(`avatar_${id}`)} onClick={() => setOnboardAvatar(id)}><img src={AVATAR_SRC[id]} alt="" /><span>{t(`avatar_${id}`)}</span></button>)}</div></div>
        <button className="button primary onboarding-submit" disabled={!onboardName.trim()}><span>{t('onboardingStart')}</span><Icon name="send" size={16} /></button>
        <small className="onboarding-note">{t('onboardingNote')}</small>
      </form>
    </div>}
    {codePreview && <Dialog title={t('codePreviewTitle')} className="preview-dialog" onClose={() => setCodePreview(null)} t={t}><div className="preview-controls"><div className="settings-tabs"><button className={previewTab === 'preview' ? 'active' : ''} aria-pressed={previewTab === 'preview'} onClick={() => setPreviewTab('preview')}><Icon name="eye" size={16} />{t('preview')}</button><button className={previewTab === 'code' ? 'active' : ''} aria-pressed={previewTab === 'code'} onClick={() => setPreviewTab('code')}><Icon name="code" size={16} />{codePreview.language}</button></div><div className="button-row"><IconButton icon="copy" label={t('copyCode')} onClick={() => copy(codePreview.text)} /><IconButton icon="download" label={t('downloadCode')} onClick={() => downloadCode(codePreview.text, codePreview.language)} /></div></div><p className="preview-note">{t('previewNote')}</p>{previewTab === 'preview' ? <iframe title={t('previewFrame')} srcDoc={previewDocument(codePreview)} sandbox="allow-scripts" referrerPolicy="no-referrer" /> : <pre className="preview-code" dir="ltr"><code>{codePreview.text}</code></pre>}</Dialog>}
    {notice && <div className={`toast ${notice.error ? 'toast-error' : ''}`} role={notice.error ? 'alert' : 'status'}><Icon name={notice.error ? 'info' : 'check'} size={18} /><span>{notice.text}</span><IconButton icon="close" label={t('closeNotice')} onClick={() => { clearTimeout(noticeTimer.current); setNotice(null) }} /></div>}
  </div>
}
