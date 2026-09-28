"""LOG-C2-031 — deterministic domain services (no framework imports).

物効法コンプライアンス KB + 特定荷主閾値計算:
- ButsurikoKB: 2024 年改正物流効率化促進法(物効法)+ 特定荷主指定方法論 + 国交省(MLIT)
  ガイドラインの seeded knowledge base。決定論検索(keyword/tag scoring)で引用可能。
- ThresholdCalculator: 特定荷主該当判定を **決定論的に**計算(年間貨物輸送量 [トンキロ換算]
  を閾値と照合)。LLM 非依存 = 監査可能。

No credentials/PII. Deterministic; LLM (production) reserved for answer phrasing only.
"""

from __future__ import annotations

from typing import Any

# 特定荷主指定の閾値(改正物効法・特定荷主指定方法論)。
# 年間の貨物輸送量(トンキロ)が基準以上の荷主が「特定荷主」に指定される。
# 数値は方法論 KB に基づく seed 値(実運用では最新政令値に更新)。
DESIGNATED_SHIPPER_THRESHOLD_TON_KM = 9_000_000  # 年間トンキロ

# ── seeded 物効法 KB ──────────────────────────────────────────────────────────
# Each record: {doc_ref, source, article, obligation_types, tags, text}
KB: list[dict[str, Any]] = [
    {
        "doc_ref": "BUTSURIKO-A15-001",
        "source": "物流効率化促進法(2024 改正)",
        "article": "第15条",
        "obligation_types": ["eligibility", "obligation"],
        "tags": ["特定荷主", "指定", "荷主", "designated", "shipper", "義務"],
        "text": "改正物効法第15条は、貨物輸送量が政令で定める基準以上の荷主を「特定荷主」として指定し、輸送の効率化に関する中長期計画の作成・定期報告を義務づける。",
    },
    {
        "doc_ref": "BUTSURIKO-METHOD-002",
        "source": "特定荷主指定方法論(国交省)",
        "article": "算定方法",
        "obligation_types": ["threshold", "eligibility"],
        "tags": ["閾値", "算定", "トンキロ", "輸送量", "threshold", "基準"],
        "text": "特定荷主の該当判定は、年間の貨物輸送量(トンキロ)を算定し、政令基準(年間トンキロ)以上か否かで判定する。委託輸送分を含め自社が荷主となる貨物を合算する。",
    },
    {
        "doc_ref": "BUTSURIKO-PLAN-003",
        "source": "物流効率化促進法(2024 改正)",
        "article": "第16条",
        "obligation_types": ["obligation", "deadline"],
        "tags": ["中長期計画", "計画", "作成", "plan", "義務", "提出"],
        "text": "特定荷主は指定後、輸送効率化に係る中長期計画を作成し所管大臣へ提出する義務を負う。計画には積載率向上・モーダルシフト等の措置を記載する。",
    },
    {
        "doc_ref": "MLIT-DEADLINE-004",
        "source": "国交省ガイドライン",
        "article": "報告期限",
        "obligation_types": ["deadline", "obligation"],
        "tags": ["期限", "定期報告", "年度", "deadline", "報告", "提出"],
        "text": "特定荷主は毎年度、輸送量および効率化措置の実施状況を定期報告する。報告は原則として当該年度終了後の所定期日までに行う。",
    },
    {
        "doc_ref": "MLIT-RESPONSIBLE-005",
        "source": "国交省ガイドライン",
        "article": "責任者選任",
        "obligation_types": ["obligation"],
        "tags": ["責任者", "選任", "統括", "officer", "体制", "義務"],
        "text": "特定荷主は物流統括管理者(責任者)を選任し、社内の輸送効率化体制を統括させる。選任は指定後速やかに行う。",
    },
    {
        "doc_ref": "BUTSURIKO-SCOPE-006",
        "source": "物流効率化促進法(2024 改正)",
        "article": "適用範囲",
        "obligation_types": ["eligibility", "general"],
        "tags": ["適用", "範囲", "対象", "scope", "荷主", "定義"],
        "text": "本法の荷主とは、自らの事業に関して貨物の輸送を委託し、又は自ら輸送する者をいう。基準未満の荷主は特定荷主に指定されないが、努力義務の対象となる。",
    },
]

_OBLIGATION_LEXICON = {
    "eligibility": ("該当", "対象", "指定される", "特定荷主か", "eligible", "適用される"),
    "threshold": ("閾値", "基準", "トンキロ", "輸送量", "計算", "算定", "何トン", "threshold"),
    "obligation": ("義務", "しなければ", "作成", "選任", "計画", "何をすれば", "obligation"),
    "deadline": ("期限", "いつまで", "報告", "提出期日", "年度", "deadline"),
}


class ButsurikoKB:
    """Deterministic retrieval over the seeded 物効法 KB."""

    @staticmethod
    def classify_obligation(query: str) -> str:
        """Rule-based obligation-type classification (LLM assists only when ambiguous)."""
        q = query or ""
        best, best_score = "general", 0
        for otype, terms in _OBLIGATION_LEXICON.items():
            score = sum(1 for t in terms if t in q)
            if score > best_score:
                best, best_score = otype, score
        return best

    @staticmethod
    def retrieve(query: str, obligation_type: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Keyword/tag + obligation-type scored retrieval. [] when nothing matches."""
        q = query or ""
        scored: list[tuple[int, dict[str, Any]]] = []
        for rec in KB:
            tag_score = sum(2 for t in rec["tags"] if t in q)
            if tag_score == 0:
                # No keyword overlap → not relevant. The obligation-type bonus is a ranking
                # boost, never an inclusion criterion (otherwise every "general" query matches).
                continue
            score = tag_score + (3 if obligation_type in rec["obligation_types"] else 0)
            scored.append((score, rec))
        scored.sort(key=lambda x: (-x[0], x[1]["doc_ref"]))
        out = []
        for score, rec in scored[:top_k]:
            out.append(
                {
                    "doc_ref": rec["doc_ref"],
                    "source": rec["source"],
                    "article": rec["article"],
                    "text": rec["text"],
                    "score": score,
                }
            )
        return out


class ThresholdCalculator:
    """Deterministic 特定荷主 threshold judgement (no LLM)."""

    @staticmethod
    def evaluate(transport_ton_km: float | None) -> dict[str, Any]:
        """Return {computable, qualifies, threshold, transport_ton_km, trace}.

        `qualifies` is None when the caller did not supply a transport volume.
        """
        threshold = DESIGNATED_SHIPPER_THRESHOLD_TON_KM
        if transport_ton_km is None:
            return {
                "computable": False,
                "qualifies": None,
                "threshold": threshold,
                "transport_ton_km": None,
                "trace": "輸送量(トンキロ)未提示のため該当判定は不可。方法論に基づき数値提示で判定可能。",
            }
        qualifies = float(transport_ton_km) >= threshold
        trace = (
            f"年間輸送量 {transport_ton_km:,.0f} トンキロ "
            f"{'≥' if qualifies else '<'} 基準 {threshold:,.0f} トンキロ "
            f"→ {'特定荷主に該当' if qualifies else '特定荷主に非該当(努力義務対象)'}"
        )
        return {
            "computable": True,
            "qualifies": qualifies,
            "threshold": threshold,
            "transport_ton_km": float(transport_ton_km),
            "trace": trace,
        }
