'use strict';
const $ = (id) => document.getElementById(id);
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const cap = (s) => s ? s.charAt(0).toUpperCase() + s.slice(1) : '';
function tag(thing) { return `<span>${escapeHTML(cap(thing.type))}: ${escapeHTML(thing.name)}</span>`; }
function render(data) {
  $('empty-state').hidden = true;
  $('result-state').hidden = false;
  const branches = data.branches || {};
  $('summary').innerHTML = [
    `Anchor: ${data.artist.name}`, `City: ${data.city}`,
    ...['movie','brand','place'].map((k) => `${k}: ${(branches[k] || []).length}`),
    `${data.concepts.length} concepts`, `${data.elapsed_ms} ms`
  ].map((item) => `<span class="pill">${escapeHTML(item)}</span>`).join('');
  $('warnings').innerHTML = (data.warnings || []).map((w) => `<div class="warning">${escapeHTML(w.branch)}: ${escapeHTML(w.detail)}</div>`).join('');
  $('cards').innerHTML = data.concepts.length ? data.concepts.map((c, i) => `
    <article class="card"><div class="card-num">PROPOSAL / 0${i+1}</div>
      <h3>${escapeHTML(c.title)}</h3><p class="format">${escapeHTML(c.format)}</p>
      <p>${escapeHTML(c.description)}</p><div class="evidence-tags">${c.evidence.map(tag).join('')}</div>
      <p><b>Why this was selected:</b> ${escapeHTML(c.decision_reason || "")}</p>
      <p><b>Qloo evidence:</b> ${escapeHTML(c.facts_from_qloo)}</p>
      <p><b>Creative inference:</b> ${escapeHTML(c.creative_inference)}</p>
      <p><b>Still to verify:</b> ${c.checks_required.map(escapeHTML).join('; ')}.</p>
      <div class="note">${escapeHTML(c.confidence_note)}</div>
    </article>`).join('') : '<div class="warning">Not enough cross-domain evidence for a supported proposal. Try another anchor or city.</div>';
  const a = data.agent_review || {};
  $('agent-review').innerHTML = `<div class="decision-summary"><strong>${escapeHTML(a.mode === 'bounded_llm' ? 'Bounded LLM reviewer · active' : 'Verified editorial rules · active')}</strong><p>${escapeHTML(a.mode === 'bounded_llm' ? 'AI selected the programme formats; deterministic code validated and allocated Qloo evidence.' : 'No validated LLM selection was applied. The deterministic goal-aware reviewer selected the formats.')}</p><p>Review status: ${escapeHTML(a.status || 'not_configured')}. ${escapeHTML(a.evidence_policy || '')}</p></div>`;
  const dec = data.decision || {};
  const intent = dec.intent || {};
  $('decision').innerHTML = `
    <div class="decision-summary"><strong>Goal policy: ${escapeHTML(intent.primary || 'unknown')}</strong>
      <p>${escapeHTML(dec.considered ?? 0)} draft formats reviewed; ${escapeHTML(dec.selected ?? 0)} selected. ${escapeHTML(dec.caveat || '')}</p>
      ${(intent.constraints || []).map(c => `<p>Verification needed: ${escapeHTML(c.replaceAll('_',' '))}</p>`).join('')}
    </div>
    ${(dec.rejected || []).map(x => `<div class="review-row"><b>${escapeHTML(x.item)}</b> — ${escapeHTML(x.reason)}</div>`).join('')}
    <div class="decision-summary"><strong>Evidence allocation · distinct where possible</strong>
      <p>Each line shows the Qloo entities allocated to one concept. Entity co-occurrence across queries does not prove a relationship between them.</p></div>
    ${(dec.diversity_audit || []).map((x, i) => `<div class="review-row"><b>Proposal ${i+1}</b> — ${escapeHTML([x.movie,x.brand,x.venue].filter(Boolean).join(' · '))}${x.reused.length ? ' (reused: '+escapeHTML(x.reused.join(', '))+')' : ''}</div>`).join('')}
  `;
  const items = [data.artist, ...['movie','brand','place'].flatMap((k) => branches[k] || [])];
  $('evidence').innerHTML = items.map((e) => `<div class="evidence-row"><strong>${escapeHTML(e.name)}</strong><span>${escapeHTML(e.type)} · ${escapeHTML(e.source)}${e.type==='place'?' · '+escapeHTML(e.venue_review?.tier || ''):''} · ${e.explainability_present?'signal trace':'search'}</span></div>`).join('') + '<div class="note">Signal traceability is not a numeric compatibility score. No venue or partnership has been confirmed.</div>';
  $('trace').innerHTML = data.trace.map((t) => `<div class="trace-row"><b>${escapeHTML(t.phase.toUpperCase())}</b> — ${escapeHTML(t.detail)} (${escapeHTML(t.status)})</div>`).join('');
}
async function refreshKeyMode() {
  try {
    const res = await fetch('/health', {cache:'no-store'});
    const state = await res.json();
    if (state.server_key_configured) $('key-field').hidden = true;
  } catch { /* Server errors are shown when submitting */ }
}
$('research-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('submit').disabled = true;
  $('submit-label').textContent = 'Researching Qloo...';
  $('status').textContent = 'Resolving your anchor and querying three evidence branches...';
  try {
    const payload = {
      artist: $('artist').value.trim(), city: $('city').value.trim(),
      objective: $('objective').value.trim(), api_key: $('api-key').value.trim()
    };
    const response = await fetch('/api/program', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      cache:'no-store', body: JSON.stringify(payload)
    });
    // Never persist or display the credential.
    payload.api_key = '';
    $('api-key').value = '';
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
    render(data);
    $('status').textContent = `Done: ${data.concepts.length} proposals grounded in live Qloo results.`;
  } catch (error) {
    $('status').textContent = `Error: ${error.message}. Please check the key and try again.`;
  } finally {
    $('submit').disabled = false;
    $('submit-label').textContent = 'Explore connections';
  }
});
refreshKeyMode();

const PRESET_GOALS = {
  film: 'Create a cinema and film screening programme that connects music and film.',
  audio: 'Design an immersive audio and sound installation for a cultural venue.',
  education: 'Develop an educational workshop and learning programme for local audiences.',
};
document.querySelectorAll('[data-goal]').forEach(button => {
  button.addEventListener('click', () => {
    const goal = PRESET_GOALS[button.dataset.goal];
    if (goal) $('objective').value = goal;
  });
});
