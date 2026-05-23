import os
import json
import time
import urllib.request
import urllib.parse
from typing import Union, Optional

from fastapi import FastAPI, Header
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai


# =========================
# 환경변수 로드
# =========================

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
APP_SECRET = os.getenv("APP_SECRET")

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

app = FastAPI(title="스꾸센스픽 API")


# =========================
# MBTI 성향 딕셔너리
# =========================

MBTI_TRAITS = {
    "INFP": "감성적이고 예술적인 것을 좋아하며 개인적인 의미의 선물을 선호함",
    "ENFP": "새롭고 흥미로운 경험을 좋아하며 서프라이즈나 창의적인 선물을 선호함",
    "INFJ": "진정성 있고 깊은 의미가 담긴 선물이나 세심한 배려가 돋보이는 아이템 선호",
    "ENFJ": "사람들과 함께 즐길 수 있거나 자기 계발에 도움을 주는 따뜻한 선물 선호",
    "INTJ": "논리적이고 지적인 호기심을 채워주거나 디자인이 깔끔하고 완성도 높은 선물 선호",
    "ENTJ": "실용적이고 목표지향적이며 생활의 효율성을 극대화해주는 선물 선호",
    "INTP": "자신의 관심 분야에 깊이 빠져들 수 있는 전문적인 도구나 독특한 아이템 선호",
    "ENTP": "평범하지 않고 기발하거나 최신 트렌드를 반영한 스마트 기기 및 아이디어 상품 선호",
    "ISFP": "오감을 만족시키는 향수, 디저트, 촉감이 좋은 물건 등 미적 감각이 있는 선물 선호",
    "ESFP": "즉각적인 즐거움을 주거나 파티, 모임에서 돋보일 수 있는 화려하고 핫한 아이템 선호",
    "ISTP": "직접 조립하거나 조작할 수 있는 기기, 취미 생활에 바로 쓸 수 있는 실용적 도구 선호",
    "ESTP": "활동적이고 스릴 있는 경험을 위한 스포츠 용품이나 직관적으로 멋진 브랜드 아이템 선호",
    "ISFJ": "일상생활에서 자주 쓸 수 있고 내구성이 좋으며 따뜻한 정성이 느껴지는 실용템 선호",
    "ESFJ": "대중적으로 인기가 많고 누구나 좋아할 만한 검증된 브랜드의 선물 세트 선호",
    "ISTJ": "오래 쓸 수 있고 기능이 확실하며 가성비와 실용성이 완벽하게 보장된 클래식 아이템 선호",
    "ESTJ": "업무나 일상에 명확한 도움이 되며 품질이 우수하고 직관적인 기능성 선물 선호",
    "모름": "특정 성향에 치우치지 않은 호불호 없는 대중적이고 안전한 베스트셀러 선물 선호",
}


# =========================
# 요청 데이터 형식
# =========================

class GiftRequestData(BaseModel):
    gender: str
    age: Union[int, str]
    relation: str = ""
    mbti: str = "모름"
    min_budget: int
    max_budget: int
    interests: str = ""
    purpose: str = ""
    avoid: str = "없음"


class ShoppingRequestData(BaseModel):
    keyword: str
    min_budget: int
    max_budget: int


# =========================
# 공통 인증 체크
# =========================

def check_app_secret(x_app_secret: Optional[str]):
    """
    APP_SECRET을 .env에 설정한 경우에만 검사.
    APP_SECRET을 비워두면 인증 없이 테스트 가능.
    """
    if APP_SECRET and x_app_secret != APP_SECRET:
        return False
    return True


# =========================
# 프롬프트 생성
# =========================

def generate_prompt(data: GiftRequestData):
    mbti_hint = MBTI_TRAITS.get(
        data.mbti.upper(),
        "호불호 없는 대중적이고 실용적인 선물 선호"
    )

    interests = data.interests.strip() if data.interests and data.interests.strip() else "특별한 관심사 없음"
    purpose = data.purpose.strip() if data.purpose and data.purpose.strip() else "일반 선물"
    avoid = data.avoid.strip() if data.avoid and data.avoid.strip() else "없음"

    if interests == "특별한 관심사 없음":
        interest_instruction = """
        🔥 [최우선 필수 지침 - 반드시 지킬 것!]
        1. 사용자가 특정 관심사를 선택하지 않았으므로, 관심사에 과하게 의존하지 말고 나이, 성별, 관계, MBTI, 예산, 선물 목적을 종합해서 추천하세요.
        2. 너무 성의 없어 보이는 뻔한 기성품(예: 아무 설명 없는 기프티콘, 무난한 핸드크림, 흔한 디퓨저 등)만 반복해서 추천하지 마세요.
        3. 받는 사람 입장에서 "내 돈 주고 사긴 아깝지만 받으면 기분 좋은" 센스 있고 대중적인 선물을 추천하세요.
        """
    else:
        interest_instruction = f"""
        🔥 [최우선 필수 지침 - 반드시 지킬 것!]
        1. 추천하는 3가지 선물은 반드시 수신자의 핵심 관심사({interests})와 "직접적이고 깊게" 연관된 실용적인 아이템이어야 합니다.
        2. 관심사를 무시하고 단순히 나이나 예산에만 끼워 맞춘 뻔한 기성품(예: 무난한 핸드크림, 디퓨저, 단순 기프티콘 등)은 절대 추천하지 마세요.
        3. 해당 관심사 분야를 실제로 즐기는 사람들이 요즘 트렌디하게 소비하거나, "내 돈 주고 사긴 아깝지만 받으면 너무 좋은" 센스 있는 아이템을 고민해서 제안해 주세요.
        """

    return f"""
    당신은 센스 있는 선물 추천 전문가입니다. 사용자의 다음 조건을 바탕으로 선물을 추천해주세요.

    [받는 사람] 나이: {data.age}세, 성별: {data.gender}, 관계: {data.relation}
    [MBTI 성향] {data.mbti} ({mbti_hint})
    [예산 범위] {data.min_budget}원 ~ {data.max_budget}원
    [취미/관심사] {interests}
    [선물 목적] {purpose}
    [기피 요소] {avoid}

    {interest_instruction}

    위 조건에 딱 맞는 구체적인 선물 상품 3가지를 추천해주세요.
    각 상품의 name은 구체적으로 작성하되, search_keyword는 네이버 쇼핑 검색용으로 반드시 짧고 넓은 키워드만 작성하세요.

    [search_keyword 작성 규칙]
    1. search_keyword는 반드시 1~3단어 이내로 작성하세요.
    2. 문장형 설명, 수식어 나열, 재질/기능/조건을 길게 붙이는 표현은 금지합니다.
    3. 브랜드명, 모델명, 색상, 재질, 세부 기능은 가급적 제외하세요.
    4. 네이버 쇼핑에서 검색 결과가 많이 나오는 일반 카테고리명으로 작성하세요.
    5. 좋은 예: "독서대", "고급 독서대", "A5 노트", "무선 이어폰", "핸드크림", "가죽 지갑"
    6. 나쁜 예: "높이/각도 조절 가능한 원목 또는 알루미늄 독서대", "감성적인 디자인의 프리미엄 필기용 노트", "20대 여성을 위한 향기 좋은 핸드크림"

    반드시 아래 JSON 형식에 맞춰서 대답해야 하며, 마크다운(```json) 없이 순수 JSON 텍스트만 출력하세요.

    {{
      "products": [
        {{
          "name": "구체적인 상품명 (브랜드 또는 핵심 키워드 포함)",
          "reason": "이 상품을 추천하는 심리적/상황적 분석 및 기대 반응 (2줄 이내)",
          "search_keyword": "네이버 쇼핑 검색용 짧은 키워드. 반드시 1~3단어. 예: '독서대', '고급 독서대', 'A5 노트', '무선 이어폰'"
        }}
      ]
    }}
    """


# =========================
# Gemini 호출
# =========================

def call_gemini_api(prompt: str):
    if not client:
        return None, "Gemini API 키가 로드되지 않았습니다. 서버의 .env 파일을 확인해 주세요."

    max_retries = 5

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )

            text = response.text.strip()

            if text.startswith("```json"):
                text = text[7:-3]
            elif text.startswith("```"):
                text = text[3:-3]

            return json.loads(text.strip()), None

        except Exception as e:
            print(f"Gemini API 오류 또는 서버 혼잡: {attempt + 1}/{max_retries}")

            if attempt == max_retries - 1:
                return None, str(e)

            time.sleep(5)


# =========================
# 네이버 쇼핑 검색
# =========================

def search_naver_shopping(keyword: str, min_budget: int, max_budget: int):
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        print("❌ 네이버 키 없음")  # 추가
        return []

    print(f"✅ 네이버 키 확인됨: ID={NAVER_CLIENT_ID[:5]}...")  # 추가

    # 검색 결과를 중복 없이 한 번 모아두기
    all_products = []
    over_budget_products = []
    seen_links = set()

    # 너무 좁은 키워드일 때 대비해서 보조 검색어도 함께 사용
    search_keywords = [keyword, f"{keyword} 선물", f"고급 {keyword}", ]

    for search_keyword in search_keywords:
        enc_text = urllib.parse.quote(search_keyword)

        # 정확도 순으로 여러 페이지 훑기
        for start in [1, 101, 201, 301]:
            url = (
                "https://openapi.naver.com/v1/search/shop.json"
                f"?query={enc_text}&display=100&start={start}&sort=sim"
            )

            request = urllib.request.Request(url)
            request.add_header("X-Naver-Client-Id", NAVER_CLIENT_ID)
            request.add_header("X-Naver-Client-Secret", NAVER_CLIENT_SECRET)

            try:
                response = urllib.request.urlopen(request, timeout=5)
                rescode = response.getcode()
                print(f"네이버 응답 코드: {rescode}")  # 추가

                if rescode != 200:
                    print(f"❌ 네이버 응답 실패: {rescode}")  # 추가
                    continue

                response_body = response.read()
                data = json.loads(response_body.decode("utf-8"))
                search_results = data.get("items", [])

                for product in search_results:
                    current_price = int(product.get("lprice", 0))
                    print(f"상품: {product.get('title', '')[:20]} | 가격: {current_price}원")  # 추가
                    link = product.get("link", "")

                    if link in seen_links:
                        continue

                    seen_links.add(link)

                    current_price = int(product.get("lprice", 0))

                    # main.py 기존 코드와 호환되도록 네이버 원본 키 이름 유지
                    item = {
                        "title": product.get("title", ""),
                        "link": product.get("link", ""),
                        "image": product.get("image", ""),
                        "lprice": str(current_price),
                        "mallName": product.get("mallName", ""),
                        "brand": product.get("brand", ""),
                        "maker": product.get("maker", ""),
                        "category1": product.get("category1", ""),
                        "category2": product.get("category2", ""),
                        "category3": product.get("category3", ""),
                        "category4": product.get("category4", ""),
                    }

                    all_products.append(item)

                    # 예산 초과 fallback용
                    if current_price > max_budget:
                        over_item = item.copy()
                        over_item["is_over_budget"] = True
                        over_budget_products.append(over_item)

            except Exception as e:
                print(f"네이버 API 연동 에러: {e}")
                continue

    # 1순위: 예산 ±10%
    for tolerance in [0.10, 0.30, 0.50]:
        allowed_min = min_budget * (1 - tolerance)
        allowed_max = max_budget * (1 + tolerance)
        print(f"허용 범위 {int(tolerance * 100)}%: {allowed_min}원 ~ {allowed_max}원")  # 추가
        print(f"전체 수집 상품 수: {len(all_products)}")  # 추가

        matched_products = []

        for item in all_products:
            current_price = int(item.get("lprice", 0))

            if allowed_min <= current_price <= allowed_max:
                # 10%, 30%, 50% 중 어떤 범위에서 잡혔는지 서버 내부 확인용
                item["budget_tolerance"] = f"{int(tolerance * 100)}%"
                matched_products.append(item)

            if len(matched_products) >= 3:
                return matched_products[:3]

        if matched_products:
            return matched_products[:3]

    # 4순위: 그래도 없으면 예산 초과 상품
    if over_budget_products:
        return over_budget_products[:3]

    return []


# =========================
# API 엔드포인트
# =========================

@app.get("/")
def root():
    return {
        "ok": True,
        "message": "스꾸센스픽 서버가 실행 중입니다."
    }


@app.get("/health")
def health():
    return {
        "ok": True,
        "gemini_ready": bool(GEMINI_API_KEY),
        "naver_ready": bool(NAVER_CLIENT_ID and NAVER_CLIENT_SECRET),
    }


@app.post("/recommend")
def recommend(
    data: GiftRequestData,
    x_app_secret: Optional[str] = Header(default=None)
):
    if not check_app_secret(x_app_secret):
        return {
            "ok": False,
            "error": "인증되지 않은 요청입니다.",
            "products": []
        }

    prompt = generate_prompt(data)
    ai_result, error_msg = call_gemini_api(prompt)

    if error_msg:
        return {
            "ok": False,
            "error": error_msg,
            "products": []
        }

    products = ai_result.get("products", [])

    return {
        "ok": True,
        "products": products
    }


@app.post("/shopping")
def shopping(
    data: ShoppingRequestData,
    x_app_secret: Optional[str] = Header(default=None)
):
    if not check_app_secret(x_app_secret):
        return {
            "ok": False,
            "error": "인증되지 않은 요청입니다.",
            "items": []
        }

    items = search_naver_shopping(
        data.keyword,
        data.min_budget,
        data.max_budget
    )

    return {
        "ok": True,
        "items": items
    }