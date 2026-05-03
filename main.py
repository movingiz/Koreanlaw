from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import os
import requests

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

function splitDefinitionText(text) {
  const t = cleanText(text);

  // "1. ... 2. ... 3. ..." 형식 분리
  const parts = t.split(/(?=\s\d+\.\s)/g)
    .map(x => x.trim())
    .filter(Boolean);

  if (parts.length >= 2) return parts;

  return [t];
}

function renderHangEnhanced(hang, keyword) {
  const hangNo = hang["항번호"] || "";
  const hangText = hang["항내용"] || "";
  const hoList = asList(hang["호"]);

  let html = `
    <details>
      <summary>제${esc(hangNo)}항 <span class="pill">${esc(shortLabel(hangText || flatten(hang), keyword))}</span></summary>
  `;

  // 호 구조가 있으면 호별로 분리 표시
  if (hoList.length > 0) {
    if (hangText) {
      html += `<pre>${esc(cleanText(hangText))}</pre>`;
    }

    for (const ho of hoList) {
      html += renderHo(ho, keyword);
    }
  }

  // 호 구조가 없는데 정의 조항처럼 "1. 2. 3."이 줄글로 들어온 경우 분리
  else {
    const defs = splitDefinitionText(hangText);

    if (defs.length > 1) {
      for (const d of defs) {
        const m = d.match(/^(\d+)\.\s*(.*)$/);
        const num = m ? m[1] : "";
        const content = m ? m[2] : d;

        html += `
          <details class="sub">
            <summary>${num ? `제${esc(num)}호` : "정의"} <span class="pill">${esc(shortLabel(content, keyword))}</span></summary>
            <pre>${esc(cleanText(content))}</pre>
          </details>
        `;
      }
    } else {
      html += `<pre>${esc(cleanText(hangText || flatten(hang)))}</pre>`;
    }
  }

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
  `;

  // 항이 없으면 조문 본문을 그대로 표시
  if (hangList.length === 0) {
    html += `
      <details open>
        <summary>조문 내용 <span class="pill">${esc(shortLabel(body || flatten(art), keyword))}</span></summary>
        <pre>${esc(cleanText(body))}</pre>
      </details>
    `;
  }

  // 항이 1개뿐인 경우: 조문 본문이 별도 실체를 가질 수 있으므로 표시
  else if (hangList.length === 1) {
    html += `
      <details>
        <summary>조문 본문 <span class="pill">${esc(shortLabel(body || flatten(art), keyword))}</span></summary>
        <pre>${esc(cleanText(body))}</pre>
      </details>
    `;
    html += renderHangEnhanced(hangList[0], keyword);
  }

  // 항이 여러 개인 경우: 조문 본문은 제목과 중복되는 경우가 많으므로 숨김
  else {
    for (const hang of hangList) {
      html += renderHangEnhanced(hang, keyword);
    }
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

function compactResultsForAi(allResults) {
  return allResults.map(r => {
    return {
      법령명: r.name,
      매칭조문: r.articles.map(a => {
        const hangList = asList(a["항"]);
        return {
          조문: `제${a["조문번호"] || ""}조${a["조문제목"] ? `(${a["조문제목"]})` : ""}`,
          항목구조: hangList.map(h => {
            const hoList = asList(h["호"]);
            return {
              항: `제${h["항번호"] || ""}항`,
              항요지: cleanText(h["항내용"] || "").slice(0, 240),
              호: hoList.map(ho => ({
                호: `제${ho["호번호"] || ""}호`,
                호요지: cleanText(ho["호내용"] || "").slice(0, 180)
              })).slice(0, 20)
            };
          }).slice(0, 20)
        };
      }).slice(0, 20)
    };
  });
}

async function generateAiSummary(lawName, keyword, allResults) {
  const compact = compactResultsForAi(allResults);

  const res = await fetch("/ai-summary", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      lawName,
      keyword,
      results: compact
    })
  });

  const data = await res.json();

  if (!res.ok) {
    throw new Error(data.error || `AI 요약 오류 ${res.status}`);
  }

  return data.summary;
}

function renderAiSummary(text) {
  return `
    <div class="box">
      <h3>AI 요약</h3>
      <pre>${esc(text)}</pre>
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

    results.innerHTML = html;
    summary.innerHTML = renderTopSummary(allResults, lawName, keyword);

    try {
      status.textContent = "AI 요약 생성 중...";
      const aiSummary = await generateAiSummary(lawName, keyword, allResults);
      summary.innerHTML = renderAiSummary(aiSummary);
      status.textContent = "완료";
    } catch (e) {
      status.textContent = "조문 검색 완료 / AI 요약 실패";
      summary.innerHTML = renderTopSummary(allResults, lawName, keyword) +
        `<div class="box"><p class="error">AI 요약 오류: ${esc(e.message)}</p></div>`;
    }

  } catch (e) {
    status.innerHTML = `<span class="error">오류: ${esc(e.message)}</span>
      <p class="muted">법제처 API 호출 또는 조문 파싱 중 오류가 발생했습니다.</p>`;
  }
}

</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def home():
    return HTML

@app.post("/ai-summary")
async def ai_summary(request: Request):
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        return JSONResponse(
            {"error": "OPENAI_API_KEY environment variable is missing."},
            status_code=500,
        )

    payload = await request.json()

    law_name = payload.get("lawName", "")
    keyword = payload.get("keyword", "")
    results = payload.get("results", [])

    prompt = f"""
다음은 국가법령정보 API에서 검색한 법령 조문 결과입니다.

검색 법령명: {law_name}
검색 키워드: {keyword}

자료:
{results}

요청:
1. 검색 결과의 전체 조문 구조를 한국어로 간결하게 설명하세요.
2. 법률, 시행령, 시행규칙이 각각 어떤 역할을 하는지 구분해서 설명하세요.
3. 하위규범이 법률 조항을 어떻게 구체화하는지 설명하세요.
4. 실무자가 우선 확인해야 할 조문을 3~7개 정도 골라 이유를 설명하세요.
5. 없는 내용은 추정하지 말고, 제공된 검색 결과 기준으로만 쓰세요.
"""

    try:
        r = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-5.5",
                "input": prompt,
            },
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()

        text = data.get("output_text")
        if not text:
            text = ""
            for item in data.get("output", []):
                for content in item.get("content", []):
                    text += content.get("text", "")

        return {"summary": text}

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
