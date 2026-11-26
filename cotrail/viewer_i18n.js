// Interface language of the viewer: English by default, Russian as the second language (the EN / RU switch, `?lang=ru`
// or `?lang=en`; the choice is remembered). Keys are the Russian strings of the page; `{0}`, `{1}` are filled by tr().
// Fixed strings in the DOM are translated as they appear (I18N.dom); strings with numbers and canvas text call tr().
const I18N = (() => {
  let lang = "en";
  try { lang = localStorage.getItem("cotrail.lang") || lang; } catch (e) {}
  const q = new URLSearchParams(location.search).get("lang");
  if (q === "ru" || q === "en") lang = q;
  const EN = {
    // page and sidebar
    "Память проекта": "Project memory", "Найти понятие": "Search concepts", "Все понятия": "All concepts",
    "Общие для тем": "Shared across topics", "Космос": "Cosmos", "Живая память": "Live memory", "Живая": "Live",
    "Тёмная": "Dark", "Светлая": "Light", "Слои": "Layers", "Разговор": "Conversation", "Код (Graphify)": "Code (Graphify)",
    "Выведенные связи": "Inferred links", "Темы": "Topics", "Журнал": "Log", "Все решения": "All decisions",
    "Панель проекта": "Project dashboard", "Цвет — тема.": "Color = topic.",
    "Разноцветный узел — понятие, общее для нескольких тем. Размер — сколько раз упоминалось. Клик по теме или узлу открывает подробности.":
      "A multicolored node is a concept shared by several topics. Size = how often it came up. Click a topic or a node for details.",
    "Квадрат — код (из Graphify).": "Square = code (from Graphify).",
    "Жёлтый пунктир — выведенная связь разговора с кодом: имя файла или символа из разговора совпало с кодом. Серый пунктир — связь в коде, которую Graphify вывел, а не извлёк.":
      "Yellow dashes = an inferred link between the conversation and the code: a file or symbol name from the chat matches the code. Gray dashes = a code link Graphify inferred rather than extracted.",
    "Приблизить": "Zoom in", "Отдалить": "Zoom out", "Весь граф": "Fit to screen",
    "{0} — {1} · {2} реплик · {3} тем": "{0} – {1} · {2} messages · {3} topics", " · {0} узлов кода": " · {0} code nodes",
    " из {0}": " of {0}", "код": "code", "вы": "you", "ассистент": "assistant",
    // decisions: one set of labels everywhere
    "Решили делать": "Decided", "Пока не / отложено": "On hold", "Решили не делать": "Ruled out", "Отложено": "On hold",
    "Все {0}": "All {0}", "Делать {0}": "Decided {0}", "Не делать {0}": "Ruled out {0}", "Отложено {0}": "On hold {0}",
    "Все": "All", "Делать": "Decided", "Не делать": "Ruled out",
    "{0} фраз · делать {1} · не делать {2} · отложено {3}": "{0} sentences · decided {1} · ruled out {2} · on hold {3}",
    // inspector
    "Тема": "Topic", "{0} понятий · {1} упоминаний · {2} решений": "{0} concepts · {1} mentions · {2} decisions",
    "Что подскажет память": "What the assistant sees", "Решения": "Decisions", "Понятия": "Concepts",
    "Это блок, который получит ассистент, если спросить про «{0}» — тот же поиск, что в инструменте {1}.":
      "This is what the assistant gets when asked about “{0}” — the same search as the {1} tool.",
    "Поиск недоступен при экспорте.": "Search isn't available in this export.",
    "Ваши фразы с признаками решения («выбираем», «не меняем», «убираем»…). Найдены правилами, без LLM — возможны пропуски и ложные.":
      "Your sentences that read like decisions (“let's go with”, “keep it as is”, “drop it”…). Found by pattern matching, no LLM — expect a few misses and false hits.",
    "Ваши фразы с признаками решения, по датам. Найдены правилами, без LLM.":
      "Your sentences that read like decisions, by date. Found by pattern matching, no LLM.",
    "Нет.": "None.", "Код · Graphify": "Code · Graphify", "Упоминается в разговоре": "Mentioned in the conversation",
    "(выведенные связи, по совпадению имени)": "(inferred, by name match)", "Нет совпадений с понятиями разговора.": "No match with the conversation's concepts.",
    "Решения об этом": "Decisions about this", "Связи в коде": "Code links", "Общее понятие": "Shared concept", "Понятие": "Concept",
    "{0} упоминаний · {1} сесс. · {2} — {3}": "{0} mentions · {1} sessions · {2} – {3}", "без темы": "no topic",
    "Решения с этим понятием": "Decisions with this concept", "В коде": "In the code", "(выведено по имени)": "(inferred by name)",
    "Последние упоминания": "Latest mentions", "Связано с": "Related to",
    "запись": "record", "Отчёт: {0}": "Report: {0}", "Меняет решение": "Replaces an earlier decision", "Решение изменено позже": "Replaced later",
    "Полностью — в ассистенте: {0}.": "Full text: {0} in the assistant.", "Ваша реплика": "Your message", "Ответ ассистента": "Assistant's reply",
    "{0} записей": "{0} records",
    // cosmos
    "Обзор": "Overview", "Панель": "Dashboard", "Вернуть вид": "Reset view", "Пауза вращения": "Pause rotation", "Вращать": "Rotate",
    "Во весь экран": "Full screen", "Доброй ночи": "Working late?", "Доброе утро": "Good morning", "Добрый день": "Good afternoon",
    "Добрый вечер": "Good evening", "С последнего визита нового нет. Последняя активность — {0}.": "Nothing new since your last visit. Last activity: {0}.",
    "За последнюю неделю нового нет. Последняя активность — {0}.": "Nothing new in the last week. Last activity: {0}.",
    "С последнего визита: {0} реплик и {1} решений": "Since your last visit: {0} messages and {1} decisions",
    "С прошлой недели проекта: {0} реплик и {1} решений": "In the project's last week: {0} messages and {1} decisions",
    " (делать — {0}, не делать — {1})": " ({0} decided, {1} ruled out)", "; больше всего про {0}.": "; mostly about {0}.", " и ": " and ",
    "Свернуть": "Collapse", "С последнего визита: {0}, {1} дн. назад": "Last visit: {0}, {1} days ago",
    "С последнего визита: сегодня или впервые — показана последняя неделя проекта": "First visit today — showing the project's last week",
    "Последние решения": "Latest decisions", "{0} решений в журнале →": "{0} decisions in the log →", "Панель проекта →": "Project dashboard →",
    "{0} понятий": "{0} concepts", "{0} узлов · Graphify": "{0} nodes · Graphify", "код · {0}": "code · {0}",
    "{0}: {1} реплик, {2} решений": "{0}: {1} messages, {2} decisions", "Реплики": "Messages", "{0} активных дней": "{0} active days",
    "+{0} за неделю": "+{0} this week", "{0} на карте · {1} тем": "{0} on the map · {1} topics", "{0} общих": "{0} shared",
    "Обновлено за неделю": "Updated this week", "понятия, упомянутые за 7 дней": "concepts mentioned in the last 7 days",
    "Активность": "Activity", "Реплик в день, последние 30 дней · точки — дни с решениями": "Messages per day, last 30 days · dots mark days with decisions",
    "Темы по размеру": "Topics by size", "Понятий в теме · клик — перелететь": "Concepts per topic · click to fly there",
    "Самые связанные понятия": "Most connected concepts", "Сумма весов связей · клик — открыть": "Total link weight · click to open",
    "Пока нет.": "Nothing yet.", "Искать понятия и решения…": "Search concepts and decisions…",
    // live memory
    "решение": "decision", "смена решения": "changed decision", "отчёт": "report", "на потом": "later",
    "разговоры": "conversations", "код · Graphify": "code · Graphify", "чат": "chat", "сессия-субагент": "subagent session",
    "разговоры: старое → новое": "conversations: older → newer", "боковые ветки — сессии-субагенты": "side branches = subagent sessions",
    "код (Graphify)": "code (Graphify)", "крупнее — решения и смены решений": "bigger = decisions and changed decisions",
    "{0} — {1} · {2} записей · решений {3} · смен {4} · на потом {5}": "{0} – {1} · {2} records · {3} decisions · {4} changes · {5} later",
    " · вызовов в журнале {0}": " · {0} calls logged", "С начала": "Replay", "час": "hour", "сутки": "day", "неделя": "week",
    "месяц": "month", "всё": "all", "● эфир": "● Live", "Новые вызовы из calls.jsonl": "New calls from calls.jsonl",
    "Живой эфир — через cotrail view --live": "For live updates run cotrail view --live", "нет вызовов за период": "no calls in this period",
    "{0} зап. · {1} мс": "{0} records · {1} ms",
    "Журнал вызовов пуст. Он пишется, когда ассистент вызывает recall / expand через MCP-сервер cotrail:": "No calls logged yet. The log fills up when the assistant calls recall / expand through the cotrail MCP server:",
    "~/.cotrail/<проект>/calls.jsonl": "~/.cotrail/<project>/calls.jsonl", "Жду вызовов…": "Waiting for calls…", "Живой эфир:": "For live updates:",
    "В памяти пока нет записей.": "Memory is empty so far.", "другие темы ({0})": "other topics ({0})", "тема {0}": "topic {0}",
    "Язык": "Language",
    "делать {0} · не делать {1}": "{0} decided · {1} ruled out",
  };
  const fill = (s, a) => s.replace(/\{(\d+)\}/g, (_, i) => a[i] ?? "");
  const tr = (ru, ...a) => fill(lang === "ru" ? ru : (EN[ru] ?? ru), a);
  const norm = s => s.replace(/\s+/g, " ").trim();
  // fixed strings already in the DOM (and inserted later): exact text nodes, title and placeholder attributes
  const SKIP = ".tx, .ftip, .item, mark, code, .mono";
  function dom(root) {
    if (lang === "ru" || !root) return;
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) { const t = norm(n.nodeValue); if (!t || !(t in EN)) continue;
      const p = n.parentElement; if (p && (p.closest(SKIP) || p.closest("script,style"))) continue;
      n.nodeValue = n.nodeValue.replace(n.nodeValue.trim(), EN[t]); }
    (root.querySelectorAll ? root.querySelectorAll("[title],[placeholder]") : []).forEach(el => ["title", "placeholder"].forEach(a => {
      const v = el.getAttribute(a); if (v && EN[norm(v)]) el.setAttribute(a, EN[norm(v)]); }));
    if (root.querySelectorAll) root.querySelectorAll("option").forEach(o => { const t = norm(o.textContent); if (EN[t]) o.textContent = EN[t]; });
  }
  function set(l) { try { localStorage.setItem("cotrail.lang", l); } catch (e) {}
    const u = new URL(location.href); if (u.searchParams.has("lang")) u.searchParams.set("lang", l); location.href = u.toString(); if (!u.searchParams.has("lang")) location.reload(); }
  function watch() {
    if (lang === "ru") return; dom(document.body);
    new MutationObserver(ms => ms.forEach(m => { m.addedNodes.forEach(n => n.nodeType === 1 ? dom(n) : n.nodeType === 3 && n.parentElement && dom(n.parentElement));
      if (m.type === "attributes" && m.target.nodeType === 1) dom(m.target); }))
      .observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["title", "placeholder"] });
  }
  document.documentElement.lang = lang;
  return { tr, dom, set, watch, get lang() { return lang; } };
})();
const tr = I18N.tr;
