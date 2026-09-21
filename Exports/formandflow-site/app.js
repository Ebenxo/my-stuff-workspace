'use strict';
const form = document.querySelector('#enquiry-form');
const list = document.querySelector('#enquiries');
const draft = document.querySelector('#draft');
const review = document.querySelector('#review');
const status = document.querySelector('#demo-status');
let enquiries = [];
function replyFor(entry) {
  const service = entry.service === 'Both' ? 'a new landing page and a clearer enquiry process' : entry.service.toLowerCase() === 'new landing page' ? 'a new landing page' : 'a clearer enquiry process';
  const timing = entry.timing === 'Exploring' ? 'You’re exploring your options, so we can start by clarifying what would be useful.' : `You’re considering ${entry.timing.toLowerCase()}; we’ll discuss availability after scoping.`;
  return `Hi ${entry.name},\n\nThanks for sharing what ${entry.business} needs. You’re interested in ${service}. ${timing}\n\nWhich part of handling enquiries takes the most time today? From there, we can agree the scope, price and delivery timing. Hosting, paid tools and ongoing support are separate.\n\nThanks,\nForm & Flow`;
}
function render() {
  list.replaceChildren();
  for (const entry of enquiries) {
    const li = document.createElement('li');
    const top = document.createElement('div'); top.className = 'entry-top';
    const title = document.createElement('strong'); title.textContent = `${entry.name} · ${entry.business}`;
    const badge = document.createElement('span'); badge.className = `badge${entry.reviewed ? ' reviewed' : ''}`; badge.textContent = entry.reviewed ? 'Reviewed' : 'Needs review';
    const detail = document.createElement('div'); detail.className = 'entry-detail'; detail.textContent = `${entry.service} / ${entry.timing}${entry.sample ? ' / Fictional sample' : ' / Demo entry'}`;
    top.append(title, badge); li.append(top, detail); list.append(li);
  }
  document.querySelector('#count').textContent = `${enquiries.length} ${enquiries.length === 1 ? 'enquiry' : 'enquiries'}`;
  draft.value = replyFor(enquiries[0]);
  review.disabled = enquiries[0].reviewed;
  review.textContent = enquiries[0].reviewed ? 'Latest enquiry reviewed ✓' : 'Mark latest reviewed ✓';
}
function resetDemo() {
  enquiries = [{name:'Jamie Taylor',business:'Willow Garden Care',service:'New landing page',timing:'Next month',reviewed:false,sample:true}];
  form.reset(); render();
}
form.addEventListener('submit', event => {
  event.preventDefault();
  const data = new FormData(form);
  for (const key of ['name','business']) {
    const field = form.elements.namedItem(key);
    field.setCustomValidity(String(data.get(key)).trim() ? '' : 'Please enter fictional details.');
    if (!field.reportValidity()) return;
  }
  enquiries.unshift({name:String(data.get('name')).trim(),business:String(data.get('business')).trim(),service:String(data.get('service')),timing:String(data.get('timing')),reviewed:false,sample:false});
  render(); list.scrollTop = 0; status.textContent = 'Demo enquiry added. Your reply draft is ready; nothing was sent.';
});
form.addEventListener('input', event => { if (event.target.setCustomValidity) event.target.setCustomValidity(''); });
review.addEventListener('click', () => { enquiries[0].reviewed = true; render(); status.textContent = 'Latest enquiry marked reviewed. Nothing was sent.'; });
document.querySelector('#copy').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText(draft.value); status.textContent = 'Reply draft copied. Review it before using it.'; }
  catch { draft.focus(); draft.select(); status.textContent = 'Automatic copying is unavailable. The draft is selected; use your device’s copy command.'; }
});
document.querySelector('#reset').addEventListener('click', () => { resetDemo(); status.textContent = 'Demo reset to its original fictional sample.'; });
const briefForm = document.querySelector('#brief-form');
briefForm.addEventListener('input', event => { if (event.target.setCustomValidity) event.target.setCustomValidity(''); });
briefForm.addEventListener('submit', event => {
  event.preventDefault();
  const data = new FormData(briefForm);
  for (const key of ['businessType','manualTask']) {
    const field = briefForm.elements.namedItem(key);
    field.setCustomValidity(String(data.get(key)).trim() ? '' : 'Please add a few details.');
    if (!field.reportValidity()) return;
  }
  const text = `FORM & FLOW — PROJECT BRIEF\n\nBusiness type\n${String(data.get('businessType')).trim()}\n\nCurrent manual enquiry task\n${String(data.get('manualTask')).trim()}\n\nStarter scope to discuss\nOne mobile-friendly service landing page; one enquiry form; one enquiry destination; follow-up status and reply template; one revision; testing and handover.\n\nPrice and delivery timing follow scoping. Hosting, paid tools and ongoing support are separate.\n\nCreated locally from a portfolio concept. Nothing has been submitted or sent to Form & Flow. This is not a quote or agreement.\n`;
  const url = URL.createObjectURL(new Blob([text], {type:'text/plain;charset=utf-8'}));
  const link = document.createElement('a'); link.href = url; link.download = 'form-and-flow-project-brief.txt'; document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
  document.querySelector('#brief-status').textContent = 'Your brief download is ready. Nothing was submitted externally.';
});
resetDemo();
