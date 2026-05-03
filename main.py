from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="Korean Law Finder v1.1")

HTML = r"""
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <title>법령 조항 검색기 v1.1</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 1100px; margin: 36px auto; line-height: 1.55; }
    input, button { font-size: 16px; padding: 8px; }
    input { width: 360px; }
    button { cursor: pointer; }
    .box { border: 1px solid #ddd; border-radius: 10px; padding: 16px; margin: 14px 0; }
    .law-title { font-size: 22px; font-weight: 800; margin-top: 34px; border-top: 3px solid #222; padding-top: 18px; }
    .article { border: 1px solid #ddd; border-radius: 10px; margin: 16px 0; padding: 14px; background: #fff; }
    .article-title { font-size: 18px; font-weight: 700; margin-bottom: 10px; }
    details { margin: 8px 0; padding: 8px 10px; background: #f8f8f8; border-radius: 8px; }
    summary { cursor: pointer; font-weight: 600; }
    .sub { margin-left: 18px; }
    .muted { color: #666; }
    .error { color: #b00020; font-weight: 700; }
    .pill { display:inline-block; padding:2px 8px; border-radius:999px; background:#eee; font-size:13px; margin-left:6px; }
    pre { white-space: pre-wrap; }
  </style>
</head>
<body>
  <h2>법령 조항 검색기 v1.1</h2>
  <p class="muted">법률·시행령·시행규칙에서 키워드 포함 조문을 찾아 조문-항-호-목 구조로 보여줍니다.</p>

  <div class="box">
    <p>API 키(OC)<br><input id="oc" placeholder="예: movingizapi" /></p>
    <p>법령명<br><input id="lawName" value="도로교통법" /></p>
    <p>키워드<br><input id="keyword" value="어린이" /></p>
    <button onclick="runSearch()">검색</button>
  </div>

  <div id="status" class="muted"></div>
  <div id="summary"></div>
  <div id="results"></div>

<script>
const BASE = "https://www.law.go.kr/DRF";

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function asList(x) {
  if (!x) return [];
  return Array.isArray(x) ? x : [x];
}

function flatten(obj) {
  if (obj === null || obj === undefined) return "";
  if (typeof obj === "string" || typeof obj === "number") return String(obj);
  if (Array.isArray(obj)) return obj.map(flatten).join(" ");
  if (typeof obj === "object") return Object.values(obj).map(flatten).join(" ");
  return String(obj);
}

function cleanText(s) {
  return String(s ?? "")
    .replace(/\s+/g, " ")
    .trim();
}

function shortLabel(text, keyword) {
  const t = cleanText(text);
  if (!t) return "";
  const idx = t.indexOf(keyword);
  if (idx >= 0) {
    const start = Math.max(0, idx - 12);
    const end = Math.min(t.length, idx + keyword.length + 26);
    return t.slice(start, end) + (end < t.length ? "..." : "");
  }
  return t.slice(0, 45) + (t.length > 45 ? "..." : "");
}

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  return await res.json();
}

async function searchLaws(oc, lawName) {
  const url = `${BASE}/lawSearch.do?OC=${encodeURIComponent(oc)}&target=law&type=JSON&query=${encodeURIComponent(lawName)}&display=20`;
  const data = await fetchJson(url);
  return asList(data?.LawSearch?.law);
}

async function getLawText(oc, mst) {
  const url = `${BASE}/lawService.do?OC=${encodeURIComponent(oc)}&target=law&type=JSON&MST=${encodeURIComponent(mst)}`;
  return await fetchJson(url);
}

function classifyRelatedLaws(laws, baseName) {
  return laws.filter(law => {
    const name = law["법령명한글"] || "";
    return name === baseName || name === `${baseName} 시행령` || name === `${baseName} 시행규칙`;
  });
}

function extractArticles(lawJson, keyword) {
  const units = asList(lawJson?.법령?.조문?.조문단위);
  const out = [];

  for (const art of units) {
    if (art["조문여부"] !== "조문") continue;
    if (!flatten(art).includes(keyword)) continue;
    out.push(art);
  }
  return out;
}

function renderMok(mok, keyword) {
  const mokNo = mok["목번호"] || "";
  const mokText = mok["목내용"] || flatten(mok);
  return `
    <details class="sub">
      <summary>${esc(mokNo)}목 <span class="pill">${esc(shortLabel(mokText, keyword))}</span></summary>
      <pre>${esc(cleanText(mokText))}</pre>
    </details>`;
}

function renderHo(ho, keyword) {
  const hoNo = ho["호번호"] || "";
  const hoText = ho["호내용"] || "";
  const mokList = asList(ho["목"]);
  let html = `
    <details class="sub">
      <summary>제${esc(hoNo)}호 <span class="pill">${esc(shortLabel(hoText || flatten(ho), keyword))}</span></summary>
      <pre>${esc(cleanText(hoText || flatten(ho)))}</pre>
  `;
  for (const mok of mokList) html += renderMok(mok, keyword);
  html += `</details>`;
  return html;
}

function renderHang(hang, keyword) {
  const hangNo = hang["항번호"] || "";
  const hangText = hang["항내용"] || "";
  const hoList = asList(hang["호"]);

  let html = `
    <details>
      <summary>제${esc(hangNo)}항 <span class="pill">${esc(shortLabel(hangText || flatten(hang), keyword))}</span></summary>
      <pre>${esc(cleanText(hangText || flatten(hang)))}</pre>
  `;
  for (const ho of hoList) html += renderHo(ho, keyword);
  html += `</details>`;
  return html;
}

function renderArticle(art, keyword) {
  const no = art["조문번호"] || "";
  const title = art["조문제목"] || "";
  const body = art["조문내용"] || "";
  const hangList = asList(art["항"]);

  let html = `<div class="article">
    <div class="article-title">제${esc(no)}조${title ? `(${esc(title)})` : ""}</div>
    <details>
      <summary>조문 본문 <span class="pill">${esc(shortLabel(body || flatten(art), keyword))}</span></summary>
      <pre>${esc(cleanText(body))}</pre>
    </details>
  `;

  if (hangList.length > 0) {
    for (const hang of hangList) html += renderHang(hang, keyword);
  } else {
    html += `<p class="muted">항 구조 없음</p>`;
  }

  html += `</div>`;
  return html;
}

function renderTopSummary(allResults, lawName, keyword) {
  const totalArticles = allResults.reduce((sum, r) => sum + r.articles.length, 0);
  const lawNames = allResults.map(r => r.name).join(", ");

  return `
    <div class="box">
      <h3>검색 요약</h3>
      <p><b>${esc(lawName)}</b> 계열 법령에서 <b>${esc(keyword)}</b> 키워드를 검색했습니다.</p>
      <p>검색 대상: ${esc(lawNames)}</p>
      <p>매칭 조문 수: <b>${totalArticles}</b>건</p>
      <p class="muted">아직 AI 요약은 아니며, 검색 결과 구조 요약입니다. 이후 OpenAI API를 붙이면 이 영역을 AI 요약으로 바꿀 수 있습니다.</p>
    </div>
  `;
}

async function runSearch() {
  const oc = document.getElementById("oc").value.trim();
  const lawName = document.getElementById("lawName").value.trim();
  const keyword = document.getElementById("keyword").value.trim();

  const status = document.getElementById("status");
  const summary = document.getElementById("summary");
  const results = document.getElementById("results");

  summary.innerHTML = "";
  results.innerHTML = "";
  status.innerHTML = "";

  if (!oc || !lawName || !keyword) {
    status.innerHTML = "<span class='error'>API 키, 법령명, 키워드를 모두 입력하세요.</span>";
    return;
  }

  try {
    status.textContent = "법령 목록 검색 중...";
    const laws = await searchLaws(oc, lawName);
    const related = classifyRelatedLaws(laws, lawName);

    if (related.length === 0) {
      status.innerHTML = `<span class="error">관련 법령을 찾지 못했습니다.</span>`;
      return;
    }

    const allResults = [];
    let html = "";

    for (const law of related) {
      const name = law["법령명한글"];
      const mst = law["법령일련번호"];
      const lawType = law["법령구분명"] || "";
      const eff = law["시행일자"] || "";
      const prom = law["공포일자"] || "";

      status.textContent = `${name} 본문 조회 중...`;
      const lawJson = await getLawText(oc, mst);
      const articles = extractArticles(lawJson, keyword);

      allResults.push({ name, articles });

      html += `<div class="law-title">${esc(name)} (${esc(lawType)})</div>`;
      html += `<p class="muted">MST: ${esc(mst)} / 시행일자: ${esc(eff)} / 공포일자: ${esc(prom)} / 매칭 조문: ${articles.length}건</p>`;

      if (articles.length === 0) {
        html += `<p>키워드 "${esc(keyword)}"가 포함된 조문을 찾지 못했습니다.</p>`;
      } else {
        for (const art of articles) html += renderArticle(art, keyword);
      }
    }

    summary.innerHTML = renderTopSummary(allResults, lawName, keyword);
    results.innerHTML = html;
    status.textContent = "완료";
  } catch (e) {
    status.innerHTML = `<span class="error">오류: ${esc(e.message)}</span>
      <p class="muted">브라우저에서 법제처 API 직접 호출이 CORS 또는 네트워크 정책에 막혔을 수 있습니다.</p>`;
  }
}
</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def home():
    return HTML
