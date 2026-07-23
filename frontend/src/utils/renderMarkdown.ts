import DOMPurify from "dompurify";

/**
 * Компактный безопасный Markdown → HTML для ИИ-анализа (заголовки, списки,
 * таблицы, жирный/курсив, инлайн-код, параграфы). Результат санитайзится
 * DOMPurify по строгому allowlist тегов (без атрибутов/ссылок/скриптов).
 */
export function renderMarkdown(md: string): string {
  if (!md) return "";
  const esc = (s: string) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const inline = (s: string) =>
    esc(s)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*])\*(?!\s)([^*]+?)\*/g, "$1<em>$2</em>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");

  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const out: string[] = [];
  let inUl = false, inOl = false;
  const closeLists = () => {
    if (inUl) { out.push("</ul>"); inUl = false; }
    if (inOl) { out.push("</ol>"); inOl = false; }
  };
  const cells = (row: string) => row.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    // Таблица: строка |..|, следующая — разделитель |---|
    if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {
      closeLists();
      const header = cells(line);
      i += 2;
      const body: string[][] = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) { body.push(cells(lines[i])); i++; }
      out.push(
        "<table><thead><tr>" + header.map(h => `<th>${inline(h)}</th>`).join("") +
        "</tr></thead><tbody>" +
        body.map(r => "<tr>" + r.map(c => `<td>${inline(c)}</td>`).join("") + "</tr>").join("") +
        "</tbody></table>",
      );
      continue;
    }
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) { closeLists(); out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`); i++; continue; }
    if (/^\s*[-*]\s+/.test(line)) {
      if (!inUl) { closeLists(); out.push("<ul>"); inUl = true; }
      out.push(`<li>${inline(line.replace(/^\s*[-*]\s+/, ""))}</li>`); i++; continue;
    }
    if (/^\s*\d+\.\s+/.test(line)) {
      if (!inOl) { closeLists(); out.push("<ol>"); inOl = true; }
      out.push(`<li>${inline(line.replace(/^\s*\d+\.\s+/, ""))}</li>`); i++; continue;
    }
    if (!line.trim()) { closeLists(); i++; continue; }
    closeLists();
    out.push(`<p>${inline(line)}</p>`); i++;
  }
  closeLists();

  return DOMPurify.sanitize(out.join("\n"), {
    ALLOWED_TAGS: ["h1", "h2", "h3", "h4", "p", "ul", "ol", "li", "strong", "em", "code",
      "table", "thead", "tbody", "tr", "th", "td", "br"],
    ALLOWED_ATTR: [],
  });
}
