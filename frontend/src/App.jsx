import { useState, useRef, useEffect } from "react";

// ─── MOCK RESULT DATA ────────────────────────────────────────────
const MOCK_RESULT = {
  workload_index: 7.4,
  breakdown: { syllabus: 8.1, professor: 7.0, grades: 6.2, reddit: 8.3 },
  red_flags: [
    "No late work accepted",
    "Group project = 35% of grade",
    "Mandatory attendance with grade penalty",
  ],
  professor: {
    name: "John Smith",
    department: "Computer Science",
    rating: 4.2,
    difficulty: 3.8,
    would_take_again: 87,
    num_ratings: 143,
  },
  grade_distribution: { A: 45, B: 30, C: 15, D: 7, F: 3 },
  syllabus_summary: {
    num_assignments: 12,
    num_exams: 3,
    has_group_project: true,
    weekly_reading_hours: 4.5,
    late_policy_strict: true,
    attendance_mandatory: true,
  },
  reddit_summary:
    "Students find this course challenging but rewarding. Exams are tough and the professor moves fast. Office hours are helpful.",
};

const SUGGESTIONS = [
  "Which natural science courses won't break a cowpoke working 40hrs?",
  "Best CS electives for wranglin' machine learning?",
  "History courses where most folks ride out with an A?",
  "Easy arts credit that won't rope me into trouble?",
];

// ─── STYLES ──────────────────────────────────────────────────────
const styles = `
  @import url('https://fonts.googleapis.com/css2?family=Rye&family=Playfair+Display:ital,wght@0,400;0,700;1,400&family=Special+Elite&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:        #1a1208;
    --surface:   #251a0a;
    --surface2:  #2f2110;
    --border:    #5c3d1a;
    --gold:      #c9912a;
    --gold2:     #e8b84b;
    --red:       #8b2020;
    --cream:     #f0deb0;
    --tan:       #c4a265;
    --muted:     #7a5c38;
    --text:      #f0deb0;
    --green:     #4a7c3f;
    --danger:    #c0392b;
  }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Special Elite', cursive;
    background-image:
      repeating-linear-gradient(0deg, transparent, transparent 40px, rgba(92,61,26,0.06) 40px, rgba(92,61,26,0.06) 41px),
      repeating-linear-gradient(90deg, transparent, transparent 40px, rgba(92,61,26,0.06) 40px, rgba(92,61,26,0.06) 41px);
  }

  /* grain overlay */
  body::after {
    content: '';
    position: fixed; inset: 0; pointer-events: none; z-index: 999;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.04'/%3E%3C/svg%3E");
    opacity: 0.35;
  }

  .app { min-height: 100vh; position: relative; }

  /* ── NAV ── */
  .nav {
    display: flex; align-items: center; justify-content: space-between;
    padding: 1rem 2.5rem;
    background: var(--surface);
    border-bottom: 3px double var(--border);
    position: sticky; top: 0; z-index: 100;
    box-shadow: 0 4px 20px rgba(0,0,0,0.6);
  }
  .nav::before {
    content: '✦ ✦ ✦';
    position: absolute; bottom: -1px; left: 50%; transform: translateX(-50%);
    font-size: 0.55rem; color: var(--gold); letter-spacing: 0.5rem;
    background: var(--surface); padding: 0 0.5rem;
  }
  .logo {
    font-family: 'Rye', cursive; font-size: 1.6rem;
    color: var(--gold2); cursor: pointer; letter-spacing: 0.05em;
    text-shadow: 2px 2px 0 #000, 0 0 20px rgba(201,145,42,0.4);
    transition: text-shadow 0.2s;
  }
  .logo:hover { text-shadow: 2px 2px 0 #000, 0 0 35px rgba(201,145,42,0.7); }
  .nav-btn {
    background: transparent;
    border: 2px solid var(--border);
    color: var(--tan); font-family: 'Special Elite', cursive;
    font-size: 0.8rem; padding: 0.45rem 1rem;
    border-radius: 3px; cursor: pointer; transition: all 0.2s;
    text-transform: uppercase; letter-spacing: 0.08em;
    position: relative;
  }
  .nav-btn::before { content: '⚑ '; font-size: 0.7rem; }
  .nav-btn:hover { border-color: var(--gold); color: var(--gold2); background: rgba(201,145,42,0.08); }

  /* ── LANDING ── */
  .landing {
    display: flex; flex-direction: column; align-items: center;
    padding: 0 2rem 5rem; position: relative; overflow: hidden;
  }

  /* wanted poster hero */
  .hero {
    text-align: center; padding: 4rem 0 2.5rem;
    position: relative; width: 100%; max-width: 700px;
  }
  .wanted-badge {
    display: inline-block;
    background: var(--surface2);
    border: 3px solid var(--gold);
    border-radius: 4px;
    padding: 2rem 3rem;
    position: relative;
    box-shadow: 0 0 0 6px var(--surface2), 0 0 0 8px var(--border), 8px 8px 30px rgba(0,0,0,0.7);
    margin-bottom: 2rem;
  }
  .wanted-badge::before {
    content: 'WANTED';
    display: block;
    font-family: 'Rye', cursive; font-size: 0.9rem;
    color: var(--red); letter-spacing: 0.5em;
    margin-bottom: 0.5rem;
  }
  .wanted-badge::after {
    content: 'DEAD OR ENROLLED';
    display: block;
    font-family: 'Special Elite', cursive; font-size: 0.75rem;
    color: var(--muted); letter-spacing: 0.25em;
    margin-top: 0.75rem;
    border-top: 1px solid var(--border); padding-top: 0.6rem;
  }
  .hero-title {
    font-family: 'Rye', cursive;
    font-size: clamp(2.2rem, 7vw, 4.5rem);
    line-height: 1.1; color: var(--gold2);
    text-shadow: 3px 3px 0 #000, 0 0 40px rgba(201,145,42,0.3);
    margin: 0;
  }
  .hero-title span { color: var(--cream); display: block; font-size: 0.45em; letter-spacing: 0.15em; margin-bottom: 0.3rem; }

  .hero-sub {
    color: var(--tan); font-size: 0.95rem; max-width: 480px;
    line-height: 1.8; margin: 0 auto 2rem;
    font-family: 'Playfair Display', serif; font-style: italic;
  }

  .hero-btns { display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap; }

  .btn-primary {
    background: var(--gold); color: #1a1208; border: none;
    padding: 0.8rem 2rem; font-family: 'Rye', cursive;
    font-size: 0.85rem; border-radius: 3px; cursor: pointer;
    transition: all 0.2s; letter-spacing: 0.05em;
    box-shadow: 3px 3px 0 #000, 0 0 20px rgba(201,145,42,0.3);
    text-transform: uppercase;
  }
  .btn-primary:hover { background: var(--gold2); transform: translate(-1px,-1px); box-shadow: 4px 4px 0 #000, 0 0 30px rgba(201,145,42,0.5); }

  .btn-ghost {
    background: transparent; color: var(--tan);
    border: 2px solid var(--border);
    padding: 0.8rem 2rem; font-family: 'Special Elite', cursive;
    font-size: 0.85rem; border-radius: 3px; cursor: pointer;
    transition: all 0.2s; letter-spacing: 0.05em; text-transform: uppercase;
    box-shadow: 3px 3px 0 #000;
  }
  .btn-ghost:hover { border-color: var(--gold); color: var(--gold2); }

  /* ── DIVIDER ── */
  .rope-divider {
    width: 100%; max-width: 760px; display: flex; align-items: center;
    gap: 1rem; margin: 2rem 0; color: var(--muted); font-size: 0.75rem;
    letter-spacing: 0.2em; text-transform: uppercase;
  }
  .rope-divider::before, .rope-divider::after {
    content: '';  flex: 1; height: 2px;
    background: repeating-linear-gradient(90deg, var(--border) 0px, var(--border) 4px, transparent 4px, transparent 8px);
  }

  /* ── CHATBOT ── */
  .chatbot-section { width: 100%; max-width: 760px; }
  .chatbot-label {
    font-family: 'Rye', cursive; font-size: 0.75rem; color: var(--gold);
    text-transform: uppercase; letter-spacing: 0.15em; margin-bottom: 0.75rem;
    display: flex; align-items: center; gap: 0.6rem;
  }
  .chatbot-label::before {
    content: ''; width: 8px; height: 8px; border-radius: 50%;
    background: #4a7c3f; display: inline-block; animation: flicker 2s infinite;
    box-shadow: 0 0 6px #4a7c3f;
  }
  @keyframes flicker { 0%,100%{opacity:1;box-shadow:0 0 6px #4a7c3f} 50%{opacity:0.6;box-shadow:0 0 2px #4a7c3f} }

  .chat-window {
    background: var(--surface);
    border: 2px solid var(--border);
    border-radius: 4px;
    overflow: hidden;
    box-shadow: 6px 6px 0 #000, 0 0 40px rgba(0,0,0,0.5);
    position: relative;
  }
  .chat-window::before {
    content: '~ ~ ~ SHERIFF\'S TELEGRAPH ~ ~ ~';
    display: block; text-align: center;
    font-family: 'Rye', cursive; font-size: 0.6rem;
    color: var(--muted); letter-spacing: 0.2em;
    padding: 0.5rem; background: var(--surface2);
    border-bottom: 1px solid var(--border);
  }

  .chat-messages {
    height: 320px; overflow-y: auto; padding: 1.25rem;
    display: flex; flex-direction: column; gap: 1rem;
    scroll-behavior: smooth;
  }
  .chat-messages::-webkit-scrollbar { width: 6px; }
  .chat-messages::-webkit-scrollbar-track { background: var(--surface2); }
  .chat-messages::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

  .msg { display: flex; gap: 0.75rem; animation: fadeUp 0.3s ease; }
  @keyframes fadeUp { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:none} }
  .msg.user { flex-direction: row-reverse; }

  .msg-avatar {
    width: 32px; height: 32px; border-radius: 50%; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    font-size: 1rem; border: 2px solid var(--border);
    background: var(--surface2);
  }

  .msg-bubble {
    max-width: 82%; padding: 0.75rem 1rem;
    font-size: 0.87rem; line-height: 1.7;
    font-family: 'Special Elite', cursive;
  }
  .msg.ai .msg-bubble {
    background: var(--surface2); color: var(--cream);
    border: 1px solid var(--border); border-radius: 2px 10px 10px 10px;
  }
  .msg.user .msg-bubble {
    background: var(--gold); color: #1a1208;
    border-radius: 10px 2px 10px 10px;
    border: 1px solid var(--gold2);
  }

  .typing-indicator { display: flex; gap: 5px; padding: 0.3rem 0; align-items: center; }
  .typing-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--muted); animation: bounce 1.2s infinite; }
  .typing-dot:nth-child(2) { animation-delay: 0.2s; }
  .typing-dot:nth-child(3) { animation-delay: 0.4s; }
  @keyframes bounce { 0%,60%,100%{transform:translateY(0)} 30%{transform:translateY(-6px)} }

  .suggestions {
    padding: 0 1.25rem 0.75rem;
    display: flex; gap: 0.5rem; flex-wrap: wrap;
  }
  .suggestion-chip {
    background: var(--surface2); border: 1px solid var(--border);
    color: var(--tan); font-size: 0.72rem; font-family: 'Special Elite', cursive;
    padding: 0.35rem 0.75rem; border-radius: 2px; cursor: pointer;
    transition: all 0.2s;
  }
  .suggestion-chip:hover { border-color: var(--gold); color: var(--gold2); background: rgba(201,145,42,0.1); }

  .chat-input-row {
    display: flex; border-top: 2px solid var(--border);
    background: var(--surface2);
  }
  .chat-input {
    flex: 1; background: transparent; border: none;
    color: var(--cream); font-family: 'Special Elite', cursive;
    font-size: 0.88rem; padding: 0.9rem 1.1rem; outline: none;
  }
  .chat-input::placeholder { color: var(--muted); font-style: italic; }
  .send-btn {
    background: var(--gold); border: none; color: #1a1208;
    cursor: pointer; padding: 0 1.25rem; font-size: 1rem;
    transition: background 0.2s; font-family: 'Rye', cursive;
    font-size: 0.75rem; letter-spacing: 0.05em;
  }
  .send-btn:hover { background: var(--gold2); }
  .send-btn:disabled { opacity: 0.4; cursor: not-allowed; }

  /* ── STATS STRIP ── */
  .stats-strip {
    display: flex; gap: 3rem; margin-top: 3.5rem;
    padding: 2rem 3rem; justify-content: center;
    border: 2px solid var(--border); border-radius: 3px;
    background: var(--surface);
    box-shadow: 4px 4px 0 #000;
    position: relative;
  }
  .stats-strip::before {
    content: '— EST. 2025 —';
    position: absolute; top: -0.6rem; left: 50%; transform: translateX(-50%);
    font-family: 'Special Elite', cursive; font-size: 0.65rem;
    color: var(--gold); background: var(--bg); padding: 0 0.75rem;
    letter-spacing: 0.2em;
  }
  .stat { text-align: center; }
  .stat-num { font-family: 'Rye', cursive; font-size: 2rem; color: var(--gold2); display: block; text-shadow: 2px 2px 0 #000; }
  .stat-label { font-family: 'Special Elite', cursive; font-size: 0.65rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.1em; }

  /* ── UPLOAD PAGE ── */
  .page-wrap { max-width: 760px; margin: 0 auto; padding: 3.5rem 2rem; }
  .page-title { font-family: 'Rye', cursive; font-size: 2.2rem; color: var(--gold2); text-shadow: 2px 2px 0 #000; margin-bottom: 0.4rem; }
  .page-sub { color: var(--tan); margin-bottom: 2.5rem; font-size: 0.9rem; font-family: 'Playfair Display', serif; font-style: italic; }

  .card {
    background: var(--surface); border: 2px solid var(--border);
    border-radius: 3px; padding: 1.75rem; margin-bottom: 1.5rem;
    box-shadow: 4px 4px 0 #000; position: relative;
  }
  .card::before {
    content: ''; position: absolute; inset: 4px;
    border: 1px solid rgba(92,61,26,0.4); border-radius: 2px;
    pointer-events: none;
  }
  .card-label {
    font-family: 'Rye', cursive; font-size: 0.72rem; color: var(--gold);
    text-transform: uppercase; letter-spacing: 0.15em; margin-bottom: 1rem;
    display: block;
  }

  .drop-zone {
    border: 2px dashed var(--border); border-radius: 3px;
    padding: 2.5rem; text-align: center; cursor: pointer;
    transition: all 0.2s; position: relative;
    background: var(--surface2);
  }
  .drop-zone:hover, .drop-zone.active {
    border-color: var(--gold); background: rgba(201,145,42,0.06);
  }
  .drop-icon { font-size: 2rem; margin-bottom: 0.5rem; display: block; }
  .drop-text { color: var(--muted); font-size: 0.88rem; line-height: 1.6; }
  .drop-text strong { color: var(--cream); }
  .file-input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }

  .divider {
    display: flex; align-items: center; gap: 1rem; margin: 1.25rem 0;
    color: var(--muted); font-size: 0.72rem; letter-spacing: 0.15em; text-transform: uppercase;
  }
  .divider::before, .divider::after { content: ''; flex: 1; height: 1px; background: var(--border); }

  textarea {
    width: 100%; background: var(--surface2); border: 1px solid var(--border);
    border-radius: 3px; color: var(--cream); font-family: 'Special Elite', cursive;
    font-size: 0.85rem; padding: 1rem; resize: vertical; min-height: 120px;
    outline: none; transition: border-color 0.2s; line-height: 1.7;
  }
  textarea:focus { border-color: var(--gold); }
  textarea::placeholder { color: var(--muted); font-style: italic; }

  .input-row { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
  input[type="text"] {
    width: 100%; background: var(--surface2); border: 1px solid var(--border);
    border-radius: 3px; color: var(--cream); font-family: 'Special Elite', cursive;
    font-size: 0.88rem; padding: 0.75rem 1rem; outline: none; transition: border-color 0.2s;
  }
  input[type="text"]:focus { border-color: var(--gold); }
  input[type="text"]::placeholder { color: var(--muted); font-style: italic; }
  .input-label { font-size: 0.72rem; color: var(--tan); margin-bottom: 0.4rem; display: block; text-transform: uppercase; letter-spacing: 0.08em; font-family: 'Special Elite', cursive; }

  .analyze-btn {
    width: 100%; background: var(--gold); color: #1a1208; border: none;
    padding: 1rem; font-family: 'Rye', cursive; font-size: 1rem;
    border-radius: 3px; cursor: pointer; transition: all 0.2s; margin-top: 1.5rem;
    box-shadow: 4px 4px 0 #000; letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  .analyze-btn:hover:not(:disabled) { background: var(--gold2); transform: translate(-1px,-1px); box-shadow: 5px 5px 0 #000; }
  .analyze-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .loading-bar { height: 4px; background: var(--surface2); border-radius: 100px; margin-top: 1rem; overflow: hidden; border: 1px solid var(--border); }
  .loading-fill { height: 100%; width: 0%; background: linear-gradient(90deg, var(--gold), var(--gold2)); animation: loadbar 2.5s ease-in-out forwards; }
  @keyframes loadbar { to { width: 88%; } }

  /* ── RESULTS ── */
  .results-wrap { max-width: 900px; margin: 0 auto; padding: 3rem 2rem 6rem; }
  .back-btn {
    background: transparent; border: 2px solid var(--border); color: var(--tan);
    font-family: 'Special Elite', cursive; font-size: 0.78rem; padding: 0.5rem 1rem;
    border-radius: 3px; cursor: pointer; transition: all 0.2s; margin-bottom: 2rem;
    box-shadow: 2px 2px 0 #000;
  }
  .back-btn:hover { border-color: var(--gold); color: var(--gold2); }
  .results-title { font-family: 'Rye', cursive; font-size: 2rem; color: var(--gold2); text-shadow: 2px 2px 0 #000; margin-bottom: 0.3rem; }
  .results-sub { color: var(--muted); font-size: 0.85rem; margin-bottom: 2.5rem; font-family: 'Playfair Display', serif; font-style: italic; }

  .hero-score {
    background: var(--surface); border: 2px solid var(--border);
    border-radius: 3px; padding: 2rem; margin-bottom: 1.5rem;
    display: flex; align-items: center; gap: 2.5rem;
    box-shadow: 4px 4px 0 #000; position: relative;
  }
  .hero-score::before {
    content: ''; position: absolute; inset: 5px;
    border: 1px solid rgba(92,61,26,0.35); border-radius: 2px; pointer-events: none;
  }
  .score-ring {
    width: 110px; height: 110px; border-radius: 50%; flex-shrink: 0;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    background: var(--surface2); border: 3px solid var(--gold);
    box-shadow: 0 0 20px rgba(201,145,42,0.3), inset 0 0 20px rgba(0,0,0,0.3);
    position: relative;
  }
  .score-ring::before {
    content: ''; position: absolute; inset: 0; border-radius: 50%;
    background: conic-gradient(var(--gold2) calc(var(--pct) * 1%), var(--surface2) 0%);
    -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 12px), black calc(100% - 12px));
    mask: radial-gradient(farthest-side, transparent calc(100% - 12px), black calc(100% - 12px));
  }
  .score-num { font-family: 'Rye', cursive; font-size: 2.2rem; line-height: 1; color: var(--gold2); text-shadow: 1px 1px 0 #000; }
  .score-den { font-family: 'Special Elite', cursive; font-size: 0.68rem; color: var(--muted); }
  .score-info { flex: 1; }
  .score-label {
    font-family: 'Rye', cursive; font-size: 1.4rem; color: var(--cream);
    margin-bottom: 0.4rem; display: flex; align-items: center; gap: 0.75rem;
  }
  .pill {
    font-family: 'Special Elite', cursive; font-size: 0.65rem;
    padding: 0.2rem 0.65rem; border-radius: 2px; text-transform: uppercase; letter-spacing: 0.08em;
  }
  .pill-red { background: rgba(139,32,32,0.2); color: #e05050; border: 1px solid rgba(139,32,32,0.5); }
  .pill-green { background: rgba(74,124,63,0.2); color: #7dc46f; border: 1px solid rgba(74,124,63,0.5); }
  .score-desc { color: var(--tan); font-size: 0.87rem; line-height: 1.65; margin-bottom: 1.1rem; font-family: 'Playfair Display', serif; font-style: italic; }
  .bar-rows { display: flex; flex-direction: column; gap: 0.55rem; }
  .bar-row { display: flex; align-items: center; gap: 0.75rem; }
  .bar-name { font-family: 'Special Elite', cursive; font-size: 0.68rem; color: var(--muted); width: 75px; text-transform: uppercase; }
  .bar-track { flex: 1; height: 6px; background: var(--surface2); border-radius: 1px; overflow: hidden; border: 1px solid var(--border); }
  .bar-fill { height: 100%; border-radius: 1px; }
  .bar-val { font-family: 'Special Elite', cursive; font-size: 0.72rem; color: var(--cream); width: 28px; text-align: right; }

  .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1.25rem; margin-bottom: 1.25rem; }
  .info-card { background: var(--surface); border: 2px solid var(--border); border-radius: 3px; padding: 1.5rem; box-shadow: 3px 3px 0 #000; }
  .card-title { font-family: 'Rye', cursive; font-size: 0.65rem; color: var(--gold); text-transform: uppercase; letter-spacing: 0.15em; margin-bottom: 1.1rem; }
  .prof-name { font-family: 'Rye', cursive; font-size: 1.3rem; color: var(--cream); margin-bottom: 0.2rem; text-shadow: 1px 1px 0 #000; }
  .prof-dept { font-family: 'Special Elite', cursive; font-size: 0.68rem; color: var(--gold); text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 1.1rem; }
  .prof-stats { display: flex; gap: 1.25rem; }
  .ps { text-align: center; }
  .ps-num { font-family: 'Rye', cursive; font-size: 1.6rem; display: block; text-shadow: 1px 1px 0 #000; }
  .ps-label { font-family: 'Special Elite', cursive; font-size: 0.6rem; color: var(--muted); text-transform: uppercase; }
  .flags-card { background: var(--surface); border: 2px solid rgba(139,32,32,0.5); border-radius: 3px; padding: 1.5rem; box-shadow: 3px 3px 0 #000; }
  .flags-title { font-family: 'Rye', cursive; font-size: 0.65rem; color: var(--danger); text-transform: uppercase; letter-spacing: 0.15em; margin-bottom: 1rem; }
  .flag-row { display: flex; align-items: center; gap: 0.65rem; padding: 0.5rem 0; border-bottom: 1px solid var(--border); font-size: 0.84rem; }
  .flag-row:last-child { border-bottom: none; }
  .flag-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--danger); flex-shrink: 0; box-shadow: 0 0 4px var(--danger); }

  .grade-card { background: var(--surface); border: 2px solid var(--border); border-radius: 3px; padding: 1.5rem; margin-bottom: 1.25rem; box-shadow: 3px 3px 0 #000; }
  .grade-cols { display: flex; align-items: flex-end; gap: 0.75rem; height: 110px; margin-top: 1rem; }
  .grade-col { display: flex; flex-direction: column; align-items: center; gap: 0.35rem; flex: 1; }
  .grade-bar-vis { width: 100%; border-radius: 2px 2px 0 0; }
  .grade-letter { font-family: 'Rye', cursive; font-size: 0.7rem; color: var(--muted); }
  .grade-pct-label { font-family: 'Special Elite', cursive; font-size: 0.62rem; color: var(--cream); }

  .summary-card { background: var(--surface); border: 2px solid var(--border); border-radius: 3px; padding: 1.5rem; margin-bottom: 1.25rem; box-shadow: 3px 3px 0 #000; }
  .sum-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 0.9rem; margin-bottom: 1.1rem; }
  .sum-item { background: var(--surface2); border-radius: 2px; padding: 0.85rem; border: 1px solid var(--border); }
  .sum-val { font-family: 'Rye', cursive; font-size: 1.4rem; display: block; margin-bottom: 0.15rem; text-shadow: 1px 1px 0 #000; }
  .sum-key { font-family: 'Special Elite', cursive; font-size: 0.6rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; }
  .reddit-block { background: var(--surface2); border-left: 3px solid var(--gold); border-radius: 0 3px 3px 0; padding: 0.9rem 1.1rem; font-size: 0.85rem; color: var(--tan); line-height: 1.7; font-style: italic; font-family: 'Playfair Display', serif; }

  .results-chatbot { max-width: 900px; margin: 0 auto; }

  @media (max-width: 640px) {
    .grid2, .input-row { grid-template-columns: 1fr; }
    .hero-score { flex-direction: column; gap: 1.5rem; }
    .sum-grid { grid-template-columns: repeat(2,1fr); }
    .stats-strip { gap: 2rem; padding: 1.5rem; }
    .nav { padding: 1rem 1.25rem; }
    .wanted-badge { padding: 1.5rem 1.75rem; }
  }
`;

// ─── GEMINI CHAT FUNCTION ────────────────────────────────────────
async function callGemini(history, userText, systemContext = null) {
  console.log("Calling backend for Gemini chat...");

  // Prepend system context as a hidden first message so Gemini has full course info
  const historyToSend = systemContext
    ? [{ role: "ai", text: `[CONTEXT FOR ADVISOR — do not repeat this verbatim to the user]: ${systemContext}` }, ...history]
    : history;

  try {
    const res = await fetch(
      `http://localhost:8000/chat`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          history: historyToSend,
          user_text: userText
        }),
      }
    );

    const data = await res.json();
    console.log("Backend response:", data); // Debug: Log backend response
    
    if (!res.ok) {
      throw new Error(data.detail || "Backend returned an error");
    }
    
    return data.response || "Somethin' went wrong at the telegraph office, partner. Try again.";
  } catch (error) {
    console.error("Chat error:", error);
    throw error;
  }
}

// ─── CHATBOT COMPONENT ───────────────────────────────────────────
function ChatBot({
  context = null,
  initialGreeting = "Howdy, partner! I'm the RateMyRodeo advisor. Ask me anything about UVA courses — difficulty, workload, grade trails, or what fits your busy schedule. What're you wranglin' with today?",
}) {
  const [messages, setMessages] = useState([
    { role: "ai", text: initialGreeting },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(true);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const sendMessage = async (text) => {
    const userText = (text || input).trim();
    if (!userText || loading) return;
    setInput("");
    setShowSuggestions(false);
    setMessages((prev) => [...prev, { role: "user", text: userText }]);
    setLoading(true);

    try {
      const reply = await callGemini(messages, userText, context);
      setMessages((prev) => [...prev, { role: "ai", text: reply }]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "ai", text: "Well, shoot — the telegraph line went dead. Check your Gemini API key and try again, partner." },
      ]);
    }

    setLoading(false);
  };

  return (
    <div className="chatbot-section">
      <div className="chatbot-label">🤠 Frontier Advisor — Ask anything about UVA courses</div>
      <div className="chat-window">
        <div className="chat-messages">
          {messages.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}>
              <div className="msg-avatar">{m.role === "ai" ? "🤠" : "🧑"}</div>
              <div className="msg-bubble" style={{ whiteSpace: "pre-wrap" }}>{m.text}</div>
            </div>
          ))}
          {loading && (
            <div className="msg ai">
              <div className="msg-avatar">🤠</div>
              <div className="msg-bubble">
                <div className="typing-indicator">
                  <div className="typing-dot" /><div className="typing-dot" /><div className="typing-dot" />
                </div>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {showSuggestions && (
          <div className="suggestions">
            {SUGGESTIONS.map((s, i) => (
              <button key={i} className="suggestion-chip" onClick={() => sendMessage(s)}>{s}</button>
            ))}
          </div>
        )}

        <div className="chat-input-row">
          <input
            className="chat-input"
            type="text"
            placeholder="Mosey on in and ask somethin'..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") sendMessage(); }}
          />
          <button className="send-btn" onClick={() => sendMessage()} disabled={loading || !input.trim()}>
            Ride →
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── LANDING PAGE ────────────────────────────────────────────────
function Landing({ onStart }) {
  return (
    <div className="landing">
      <div className="hero">
        <div className="wanted-badge">
          <div className="hero-title">
            <span>Rate My</span>
            Rodeo
          </div>
        </div>
        <p className="hero-sub">
          Don't ride blind into a hard trail, partner. Upload your syllabus and get a full 360° roundup — workload score, professor rep, grade trails, and red flags — all in one saloon.
        </p>
        <div className="hero-btns">
          <button className="btn-primary" onClick={onStart}>⚑ Analyze a Syllabus</button>
          <button className="btn-ghost" onClick={() => document.querySelector(".chat-input")?.focus()}>
            Ask the Sheriff ↓
          </button>
        </div>
      </div>

      <div className="rope-divider">The Telegraph Office</div>

      <ChatBot />

      <div className="stats-strip">
        <div className="stat"><span className="stat-num">4</span><span className="stat-label">Data Sources</span></div>
        <div className="stat"><span className="stat-num">~10s</span><span className="stat-label">Roundup Time</span></div>
        <div className="stat"><span className="stat-num">1</span><span className="stat-label">Score to Rule 'Em All</span></div>
      </div>
    </div>
  );
}

// ─── UPLOAD PAGE ─────────────────────────────────────────────────
function Upload({ onAnalyze }) {
  const [syllabusText, setSyllabusText] = useState("");
  const [professor, setProfessor] = useState("");
  const [course, setCourse] = useState("");
  const [fileName, setFileName] = useState(null);
  const [loading, setLoading] = useState(false);
  const [dragging, setDragging] = useState(false);

  const handleFile = (file) => {
    if (!file) return;
    setFileName(file.name);
    const reader = new FileReader();
    reader.onload = (e) => setSyllabusText(e.target.result);
    reader.readAsText(file);
  };

  const handleSubmit = async () => {
    if (!syllabusText && !fileName) { alert("Whoa there — drop in a syllabus first, pardner."); return; }
    if (!professor) { alert("We need a name to wrangle, partner. Enter a professor."); return; }
    setLoading(true);
    
    try {
      // Send request to backend for analysis
      const response = await fetch("http://localhost:8000/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          professor_name: professor,
          course_code: course || "Unknown Course",
          syllabus_text: syllabusText
        })
      });
      
      if (!response.ok) {
        throw new Error("Backend analysis failed");
      }
      
      const result = await response.json();
      setLoading(false);
      onAnalyze({ syllabusText, professor, course, result });
    } catch (error) {
      console.error("Analysis error:", error);
      setLoading(false);
      alert("Ran into trouble analyzing that syllabus, partner. Check your backend server is running and try again.");
    }
  };

  return (
    <div className="page-wrap">
      <h2 className="page-title">Scout the Trail</h2>
      <p className="page-sub">Drop in your syllabus scroll and we'll tell you what you're ridin' into.</p>

      <div className="card">
        <span className="card-label">01 — The Syllabus Scroll</span>
        <div
          className={`drop-zone ${dragging ? "active" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); handleFile(e.dataTransfer.files[0]); }}
        >
          <input type="file" className="file-input" accept=".pdf,.txt,.doc,.docx" onChange={(e) => handleFile(e.target.files[0])} />
          <span className="drop-icon">📜</span>
          <p className="drop-text">
            {fileName
              ? <><strong>{fileName}</strong> — ready to scout</>
              : <><strong>Drop your syllabus here</strong> or click to mosey on in<br /><span style={{fontSize:"0.78rem"}}>PDF, TXT, DOC accepted at this here saloon</span></>}
          </p>
        </div>
        <div className="divider">or paste the scroll</div>
        <textarea placeholder="Paste your syllabus text here, pardner..." value={syllabusText} onChange={(e) => setSyllabusText(e.target.value)} />
      </div>

      <div className="card">
        <span className="card-label">02 — Who's Runnin' the Show</span>
        <div className="input-row">
          <div>
            <label className="input-label">Professor's Name</label>
            <input type="text" placeholder="e.g. John Smith" value={professor} onChange={(e) => setProfessor(e.target.value)} />
          </div>
          <div>
            <label className="input-label">Course Code (optional)</label>
            <input type="text" placeholder="e.g. CS 3140" value={course} onChange={(e) => setCourse(e.target.value)} />
          </div>
        </div>
      </div>

      <button className="analyze-btn" onClick={handleSubmit} disabled={loading}>
        {loading ? "⏳ Scoutin' the trail..." : "⚑ Get the Roundup Report"}
      </button>
      {loading && <div className="loading-bar"><div className="loading-fill" /></div>}
    </div>
  );
}

// ─── RESULTS PAGE ────────────────────────────────────────────────
function Results({ data, professor, course, onBack }) {
  const score = data.workload_index;
  const label = score >= 8 ? "Grueling Cattle Drive" : score >= 6 ? "Rough Trail" : score >= 4 ? "Moderate Ride" : "Easy Pasture";

  const advisorContext = [
    `You are a friendly college course advisor for UVA students, speaking in a Western/cowboy style. You have the following analysis for the student's course:`,
    `Course: ${course || "Unknown Course"}`,
    `Professor: ${data.professor.name} (${data.professor.department})`,
    `RateMyProfessor — Rating: ${data.professor.rating}/5, Difficulty: ${data.professor.difficulty}/5, Would Take Again: ${data.professor.would_take_again}% (${data.professor.num_ratings} ratings)`,
    `Workload Index: ${score}/10 (${label})`,
    `Breakdown — Syllabus: ${data.breakdown.syllabus}, Professor: ${data.breakdown.professor}, Grades: ${data.breakdown.grades}, Reddit: ${data.breakdown.reddit}`,
    `Red Flags: ${data.red_flags.join("; ")}`,
    `Grade Distribution: A:${data.grade_distribution.A}%, B:${data.grade_distribution.B}%, C:${data.grade_distribution.C}%, D:${data.grade_distribution.D}%, F:${data.grade_distribution.F}%`,
    `Syllabus: ${data.syllabus_summary.num_assignments} assignments, ${data.syllabus_summary.num_exams} exams, ${data.syllabus_summary.weekly_reading_hours}h/week reading, Late Policy: ${data.syllabus_summary.late_policy_strict ? "Strict" : "Flexible"}, Attendance: ${data.syllabus_summary.attendance_mandatory ? "Required" : "Optional"}, Group Project: ${data.syllabus_summary.has_group_project ? "Yes" : "No"}`,
    `Reddit Summary: ${data.reddit_summary}`,
    `Use this data to answer the student's follow-up questions naturally and helpfully.`,
  ].join("\n");

  const advisorGreeting = `Howdy! I've got the full roundup on ${course || "this course"} with Sheriff ${professor}. The workload clocks in at ${score}/10 — a ${label}. Ask me anything: is it doable with a part-time job? What to watch out for? I'm all ears, partner.`;
  const desc = score >= 8
    ? "This here trail is brutal, partner. Don't rope yourself into more courses without extra provisions."
    : score >= 6
    ? "Above average hardship on this trail. Budget your saddle time wisely."
    : "A manageable ride. Good pick if your saddlebags are already full.";

  const barColors = { syllabus: "#c9912a", professor: "#8b6914", grades: "#4a7c3f", reddit: "#6b4c2a" };
  const gradeColors = { A: "#4a7c3f", B: "#c9912a", C: "#8b6914", D: "#6b3030", F: "#8b2020" };
  const maxGrade = Math.max(...Object.values(data.grade_distribution));

  return (
    <div className="results-wrap">
      <button className="back-btn" onClick={onBack}>← Ride Back</button>
      <h2 className="results-title">{course || "Course Roundup"}</h2>
      <p className="results-sub">Sheriff {professor} · University of Virginia Frontier</p>

      <div className="hero-score">
        <div className="score-ring" style={{ "--pct": score * 10 }}>
          <span className="score-num">{score}</span>
          <span className="score-den">/ 10</span>
        </div>
        <div className="score-info">
          <div className="score-label">
            {label}
            <span className={`pill ${score >= 7 ? "pill-red" : "pill-green"}`}>
              {score >= 7 ? "Hard Ride" : "Smooth Trail"}
            </span>
          </div>
          <p className="score-desc">{desc}</p>
          <div className="bar-rows">
            {Object.entries(data.breakdown).map(([key, val]) => (
              <div key={key} className="bar-row">
                <span className="bar-name">{key}</span>
                <div className="bar-track"><div className="bar-fill" style={{ width: `${val * 10}%`, background: barColors[key] }} /></div>
                <span className="bar-val">{val}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid2">
        <div className="info-card">
          <div className="card-title">🤠 The Sheriff</div>
          <div className="prof-name">{data.professor.name}</div>
          <div className="prof-dept">{data.professor.department}</div>
          <div className="prof-stats">
            <div className="ps"><span className="ps-num" style={{color:"#7dc46f"}}>{data.professor.rating}</span><span className="ps-label">Rating</span></div>
            <div className="ps"><span className="ps-num" style={{color:"#c9912a"}}>{data.professor.difficulty}</span><span className="ps-label">Toughness</span></div>
            <div className="ps"><span className="ps-num" style={{color:"#e8b84b"}}>{data.professor.would_take_again}%</span><span className="ps-label">Ride Again</span></div>
          </div>
        </div>
        <div className="flags-card">
          <div className="flags-title">⚠ Wanted Posters</div>
          {data.red_flags.map((f, i) => <div key={i} className="flag-row"><span className="flag-dot" />{f}</div>)}
        </div>
      </div>

      <div className="grade-card">
        <div className="card-title">📊 Historical Grade Trail</div>
        <div className="grade-cols">
          {Object.entries(data.grade_distribution).map(([g, pct]) => (
            <div key={g} className="grade-col">
              <span className="grade-pct-label">{pct}%</span>
              <div className="grade-bar-vis" style={{ height: `${(pct / maxGrade) * 65}px`, background: gradeColors[g] }} />
              <span className="grade-letter">{g}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="summary-card">
        <div className="card-title">📜 Syllabus Scouting Report</div>
        <div className="sum-grid">
          <div className="sum-item"><span className="sum-val">{data.syllabus_summary.num_assignments}</span><span className="sum-key">Assignments</span></div>
          <div className="sum-item"><span className="sum-val">{data.syllabus_summary.num_exams}</span><span className="sum-key">Exams</span></div>
          <div className="sum-item"><span className="sum-val">{data.syllabus_summary.weekly_reading_hours}h</span><span className="sum-key">Hrs/Week</span></div>
          <div className="sum-item"><span className="sum-val" style={{color: data.syllabus_summary.late_policy_strict ? "#e05050" : "#7dc46f"}}>{data.syllabus_summary.late_policy_strict ? "Strict" : "Flexible"}</span><span className="sum-key">Late Policy</span></div>
          <div className="sum-item"><span className="sum-val" style={{color: data.syllabus_summary.attendance_mandatory ? "#e05050" : "#7dc46f"}}>{data.syllabus_summary.attendance_mandatory ? "Required" : "Optional"}</span><span className="sum-key">Attendance</span></div>
          <div className="sum-item"><span className="sum-val" style={{color: data.syllabus_summary.has_group_project ? "#c9912a" : "#7dc46f"}}>{data.syllabus_summary.has_group_project ? "Yep" : "Nope"}</span><span className="sum-key">Group Project</span></div>
        </div>
        <div className="reddit-block">"{data.reddit_summary}"</div>
      </div>

      <div className="rope-divider">Ask the Frontier Advisor</div>
      <div className="results-chatbot">
        <ChatBot context={advisorContext} initialGreeting={advisorGreeting} />
      </div>
    </div>
  );
}

// ─── ROOT ────────────────────────────────────────────────────────
export default function App() {
  const [page, setPage] = useState("landing");
  const [formData, setFormData] = useState(null);

  return (
    <>
      <style>{styles}</style>
      <div className="app">
        <nav className="nav">
          <div className="logo" onClick={() => setPage("landing")}>⭐ RateMyRodeo</div>
          {page !== "upload" && (
            <button className="nav-btn" onClick={() => setPage("upload")}>Scout a Course</button>
          )}
        </nav>
        {page === "landing" && <Landing onStart={() => setPage("upload")} />}
        {page === "upload" && <Upload onAnalyze={(d) => { setFormData(d); setPage("results"); }} />}
        {page === "results" && (
          <Results
            data={formData?.result || MOCK_RESULT}
            professor={formData?.professor}
            course={formData?.course}
            onBack={() => setPage("upload")}
          />
        )}
      </div>
    </>
  );
}