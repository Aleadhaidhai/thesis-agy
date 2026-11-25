const { createApp, ref, computed, nextTick, onMounted } = Vue;
const API = location.port === '5173' ? 'http://127.0.0.1:8000' : '';

const app = createApp({
  setup() {
    const tab = ref('im');
    const users = ref([]);
    const userId = ref(localStorage.getItem('eim_user') || 'u_xiaochen');
    const convs = ref([]);
    const convId = ref('');
    const botConv = ref('');
    const messages = ref([]);
    const draft = ref('');
    const pendingFile = ref(null);
    const thinking = ref(false);
    const highlight = ref('');
    const msgBox = ref(null);
    const humans = computed(() => users.value.filter(u => !u.is_bot));
    const convName = computed(() => convId.value === botConv.value ? '小知（知识助手）'
      : (convs.value.find(c => c.conv_id === convId.value) || {}).name);

    const get = async (u) => (await fetch(API + u)).json();
    const fmt = (ts) => ts ? new Date(ts * 1000).toLocaleString('zh-CN', { hour12: false }).slice(0, 16) : '';
    const fileUrl = (a) => `${API}/im/files/${a.file_id}`;
    const refText = (id) => { const m = messages.value.find(x => x.msg_id === id); return m ? `${m.sender_name}：${(m.text || (m.attachment || {}).name || '').slice(0, 40)}` : ''; };
    const renderText = (m) => {
      if (m.sender_id !== 'bot_xiaozhi') return m.text.replace(/</g, '&lt;').replace(/@小知/g, '<span class="at">@小知</span>');
      return marked.parse(m.text).replace(/\[(\d+)\]/g, '<sup class="ref">[$1]</sup>');
    };

    async function loadConvs() {
      convs.value = await get(`/im/convs?user_id=${userId.value}`);
      convs.value = convs.value.filter(c => c.type === 'group');
      const r = await fetch(`${API}/im/convs/p2p_bot?user_id=${userId.value}`, { method: 'POST' });
      botConv.value = (await r.json()).conv_id;
    }
    async function loadMessages(scroll = true) {
      if (!convId.value) return;
      messages.value = await get(`/im/convs/${convId.value}/messages?user_id=${userId.value}&limit=300`);
      const last = messages.value[messages.value.length - 1];
      thinking.value = !!(last && last.sender_id === userId.value && (last.text.includes('@小知') || convId.value === botConv.value));
      if (scroll) { await nextTick(); if (msgBox.value) msgBox.value.scrollTop = msgBox.value.scrollHeight; }
    }
    async function selectConv(id, hl = '') {
      convId.value = id; highlight.value = hl; await loadMessages(!hl);
      if (hl) { await nextTick(); const el = document.getElementById('m_' + hl); if (el) el.scrollIntoView({ block: 'center' }); }
    }
    const openBot = () => selectConv(botConv.value);
    async function onUserChange() {
      localStorage.setItem('eim_user', userId.value); convId.value = ''; messages.value = []; await loadConvs();
    }
    function onFile(f) { pendingFile.value = f.raw; }
    async function send() {
      if (!draft.value.trim() && !pendingFile.value) return;
      const fd = new FormData();
      fd.append('user_id', userId.value);
      let text = draft.value;
      if (convId.value === botConv.value && text && !text.includes('@小知')) text = text; // 单聊无需 @
      fd.append('text', text);
      if (pendingFile.value) fd.append('file', pendingFile.value);
      draft.value = ''; pendingFile.value = null;
      await fetch(`${API}/im/convs/${convId.value}/messages`, { method: 'POST', body: fd });
      await loadMessages();
    }
    async function jump(c) {
      const ok = c.conv_id === botConv.value || convs.value.some(x => x.conv_id === c.conv_id);
      if (!ok) { ElementPlus.ElMessage.warning('你不在该会话中，无法跳转'); return; }
      await selectConv(c.conv_id, c.msg_id);
    }
    async function feedback(id, s) {
      await fetch(`${API}/api/feedback`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ qa_id: id, score: s }) });
      ElementPlus.ElMessage.success('感谢反馈');
    }

    // ---------- admin ----------
    const stats = ref({}); const adminTab = ref('mku'); const mkus = ref([]); const qaLogs = ref([]);
    const allConvs = ref([]); const mkuConv = ref(''); const mkuKind = ref(''); const mkuQ = ref('');
    const ingesting = ref(false); const ingestResult = ref('');
    const statCards = computed(() => {
      const s = stats.value; if (!s.messages && s.messages !== 0) return {};
      return { '会话数': s.conversations, '消息数': s.messages, '话题数': s.topics, '知识单元': s.mkus,
        '向量(文本/视觉)': `${(s.vectors || {}).mku_text || 0} / ${(s.vectors || {}).mku_visual || 0}`,
        '问答次数': s.qa_total, '好评/差评': `${s.qa_like} / ${s.qa_dislike}`, '平均耗时(ms)': s.avg_latency_ms };
    });
    async function loadAdmin() {
      stats.value = await get('/admin/stats'); allConvs.value = await get('/admin/convs');
      await loadMkus(); qaLogs.value = await get('/admin/qa_logs?limit=100');
    }
    async function loadMkus() {
      const p = new URLSearchParams({ limit: 100 });
      if (mkuConv.value) p.set('conv_id', mkuConv.value); if (mkuKind.value) p.set('kind', mkuKind.value); if (mkuQ.value) p.set('q', mkuQ.value);
      mkus.value = await get('/admin/mkus?' + p);
    }
    async function ingest(full) {
      ingesting.value = true; ingestResult.value = '';
      try { const r = await (await fetch(`${API}/admin/ingest?full=${full}`, { method: 'POST' })).json();
        ingestResult.value = `新增消息 ${r.messages}，解析 ${r.parsed}，话题 ${r.topics}，知识单元 ${r.mkus}，耗时 ${r.elapsed_s}s`; }
      finally { ingesting.value = false; loadAdmin(); }
    }

    onMounted(async () => {
      users.value = await get('/im/users');
      await loadConvs();
      const ws = new WebSocket((API || location.origin).replace('http', 'ws') + '/im/ws');
      ws.onmessage = (e) => { const d = JSON.parse(e.data); if (d.conv_id === convId.value) loadMessages(); };
    });

    return { tab, users, humans, userId, convs, convId, botConv, convName, messages, draft, pendingFile, thinking,
      highlight, msgBox, fmt, fileUrl, refText, renderText, selectConv, openBot, onUserChange, onFile, send, jump,
      feedback, stats, statCards, adminTab, mkus, qaLogs, allConvs, mkuConv, mkuKind, mkuQ, ingesting,
      ingestResult, loadMkus, ingest, loadAdmin };
  },
  watch: { tab(v) { if (v === 'admin') this.loadAdmin(); } },
});
app.use(ElementPlus).mount('#app');
