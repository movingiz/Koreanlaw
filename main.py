from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="Korean Law Finder v1")

HTML = r"""
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <title>법령 조항 검색기 v1</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 1100px; margin: 36px auto; line-height: 1.55; }
    input, button { font-size: 16px; padding: 8px; }
    input { width: 360px; }
    button { cursor: pointer; }
    .box { border: 1px solid #ddd; border-radius: 10px; padding: 16px; margin: 14px 0; }
    .law-title { font-size: 20px; font-weight: 700; margin-top: 28px; border-top: 2px solid #222; padding-top: 18px; }
    pre { white-space: pre-wrap; background: #f8f8f8; padding: 12px; border-radius: 8px; overflow-wrap: anywhere; }
    .muted { color: #666; }
    .error { color: #b00020; font-weight: 700; }
  </style>
</head>
<body>
  <h2>법령 조항 검색기 v1</h2>
  <p class="muted">
    Render 서버가 아니라, 현재 브라우저가 국가법령정보 API를 직접 호출합니다.
  </p>

  <div class="box">
    <p>
      API 키(OC)<br>
      <input id="oc" placeholder="예: movingizapi" />
    </p>
    <p>
      법령명<br>
      <input id="lawName" value="도로교통법" />
    </p>
    <p>
      키워드<br>
      <input id="keyword" value="어린이" />
    </p>
    <button onclick="runSearch()">검색</button>
  </div>

  <div id="status" class="muted"></div>
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
    return (
      name === baseName ||
      name === `${baseName} 시행령` ||
      name === `${baseName} 시행규칙`
    );
  });
}

function extractArticles(lawJson, keyword) {
  const units = asList(lawJson?.법령?.조문?.조문단위);
  const out = [];

  for (const art of units) {
    if (art["조문여부"] !== "조문") continue;

    const allText = flatten(art);
    if (!allText.includes(keyword)) continue;

    out.push({
      no: art["조문번호"] || "",
      title: art["조문제목"] || "",
      body: allText.slice(0, 5000)
    });
  }

  return out;
}

async function runSearch() {
  const oc = document.getElementById("oc").value.trim();
  const lawName = document.getElementById("lawName").value.trim();
  const keyword = document.getElementById("keyword").value.trim();
  const status = document.getElementById("status");
  const results = document.getElementById("results");

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
      results.innerHTML = `<p class="error">관련 법령을 찾지 못했습니다.</p>
      <pre>${esc(JSON.stringify(laws, null, 2))}</pre>`;
      status.textContent = "";
      return;
    }

    let html = `<p>검색된 관련 법령: ${related.length}건</p>`;

    for (const law of related) {
      const name = law["법령명한글"];
      const mst = law["법령일련번호"];
      const lawType = law["법령구분명"] || "";
      const eff = law["시행일자"] || "";
      const prom = law["공포일자"] || "";

      status.textContent = `${name} 본문 조회 중...`;

      const lawJson = await getLawText(oc, mst);
      const articles = extractArticles(lawJson, keyword);

      html += `<div class="law-title">${esc(name)} (${esc(lawType)})</div>`;
      html += `<p class="muted">MST: ${esc(mst)} / 시행일자: ${esc(eff)} / 공포일자: ${esc(prom)}</p>`;

      if (articles.length === 0) {
        html += `<p>키워드 "${esc(keyword)}"가 포함된 조문을 찾지 못했습니다.</p>`;
      } else {
        html += `<p>매칭 조문: ${articles.length}건</p>`;
        for (const a of articles) {
          html += `<div class="box">
            <h3>제${esc(a.no)}조 ${esc(a.title)}</h3>
            <pre>${esc(a.body)}</pre>
          </div>`;
        }
      }
    }

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
