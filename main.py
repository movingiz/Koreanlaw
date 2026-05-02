from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
import os
import requests
from typing import Any

app = FastAPI(title="Korean Law Finder")

LAW_OC = os.getenv("LAW_OC")
BASE = "http://www.law.go.kr/DRF"

@app.get("/debug")
def debug():
    return {
        "LAW_OC": LAW_OC
    }


def normalize_list(x: Any):
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def api_get(path: str, params: dict):
    if not LAW_OC:
        raise RuntimeError("LAW_OC environment variable is missing.")

    params = {
        "OC": LAW_OC,
        "type": "JSON",
        **params,
    }
    r = requests.get(f"{BASE}/{path}", params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def search_laws(law_name: str):
    data = api_get("lawSearch.do", {
        "target": "law",
        "query": law_name,
        "display": 20,
    })
    laws = data.get("LawSearch", {}).get("law", [])
    return normalize_list(laws)


def get_law_text(mst: str):
    return api_get("lawService.do", {
        "target": "law",
        "MST": mst,
    })


def flatten_text(obj: Any) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return " ".join(flatten_text(v) for v in obj.values())
    if isinstance(obj, list):
        return " ".join(flatten_text(v) for v in obj)
    return str(obj)


def extract_articles(law_json: dict, keyword: str):
    law = law_json.get("법령", {})
    articles = law.get("조문", {}).get("조문단위", [])
    articles = normalize_list(articles)

    results = []

    for art in articles:
        if art.get("조문여부") != "조문":
            continue

        full_text = flatten_text(art)

        if keyword not in full_text:
            continue

        article_no = art.get("조문번호", "")
        article_title = art.get("조문제목", "")
        article_body = art.get("조문내용", "")

        results.append({
            "조문번호": article_no,
            "조문제목": article_title,
            "조문내용": article_body,
            "전체본문": full_text[:4000],
        })

    return results


def classify_related_laws(laws: list, base_name: str):
    wanted = []

    for law in laws:
        name = law.get("법령명한글", "")

        if name == base_name:
            wanted.append(law)
        elif name == f"{base_name} 시행령":
            wanted.append(law)
        elif name == f"{base_name} 시행규칙":
            wanted.append(law)

    return wanted


@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
      <head>
        <meta charset="utf-8" />
        <title>법령 조항 검색기</title>
      </head>
      <body style="font-family: sans-serif; max-width: 900px; margin: 40px auto;">
        <h2>법령 조항 검색기</h2>
        <form action="/find" method="get">
          <p>
            법령명<br/>
            <input name="law_name" value="도로교통법" style="width: 400px; padding: 8px;" />
          </p>
          <p>
            키워드<br/>
            <input name="keyword" value="어린이" style="width: 400px; padding: 8px;" />
          </p>
          <button type="submit" style="padding: 8px 16px;">검색</button>
        </form>
      </body>
    </html>
    """


@app.get("/find", response_class=HTMLResponse)
def find_articles(
    law_name: str = Query(...),
    keyword: str = Query(...),
):
    laws = search_laws(law_name)
    related = classify_related_laws(laws, law_name)

    if not related:
        return f"<h3>관련 법령을 찾지 못했습니다: {law_name}</h3>"

    html = [
        "<html><head><meta charset='utf-8'><title>검색 결과</title></head>",
        "<body style='font-family: sans-serif; max-width: 1000px; margin: 40px auto;'>",
        f"<h2>검색 결과: {law_name} / 키워드: {keyword}</h2>",
        "<p><a href='/'>다시 검색</a></p>",
    ]

    for law in related:
        name = law.get("법령명한글")
        mst = law.get("법령일련번호")
        law_type = law.get("법령구분명")
        eff = law.get("시행일자")

        html.append(f"<hr><h3>{name} ({law_type})</h3>")
        html.append(f"<p>시행일자: {eff} / MST: {mst}</p>")

        try:
            law_json = get_law_text(mst)
            articles = extract_articles(law_json, keyword)
        except Exception as e:
            html.append(f"<p style='color:red;'>조회 오류: {e}</p>")
            continue

        if not articles:
            html.append("<p>키워드가 포함된 조문을 찾지 못했습니다.</p>")
            continue

        for a in articles:
            title = a.get("조문제목") or ""
            no = a.get("조문번호") or ""
            body = a.get("전체본문") or ""

            html.append(
                "<div style='border:1px solid #ddd; padding:16px; margin:12px 0; border-radius:8px;'>"
            )
            html.append(f"<h4>제{no}조 {title}</h4>")
            html.append(f"<pre style='white-space:pre-wrap; line-height:1.5;'>{body}</pre>")
            html.append("</div>")

    html.append("</body></html>")
    return "\n".join(html)


@app.get("/api/find")
def find_articles_api(
    law_name: str = Query(...),
    keyword: str = Query(...),
):
    laws = search_laws(law_name)
    related = classify_related_laws(laws, law_name)

    output = []

    for law in related:
        mst = law.get("법령일련번호")
        law_json = get_law_text(mst)
        output.append({
            "law": law,
            "matched_articles": extract_articles(law_json, keyword),
        })

    return {
        "query": {
            "law_name": law_name,
            "keyword": keyword,
        },
        "results": output,
    }
