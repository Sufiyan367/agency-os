from typing import Dict, Any, List

class MarketLocalization:
    """Provides multi-lingual search queries and local business terminology."""

    LANGUAGE_QUERY_TEMPLATES: Dict[str, Dict[str, str]] = {
        "en": {
            "ai_adoption": "{country} {niche} AI automation technology adoption market report",
            "demand": "{country} commercial {niche} software solutions demand missed calls",
            "labor": "{country} {niche} industry labor shortage operational costs",
            "competition": "{country} {niche} AI automation agency providers saturation",
        },
        "ar": {
            "ai_adoption": "تبني الذكاء الاصطناعي أتمتة {country} {niche} تقرير سوق",
            "demand": "حلول برمجية أتمتة {country} {niche} شركات",
            "labor": "نقص العمالة وتكاليف التشغيل {country} {niche}",
            "competition": "شركات وكالات الذكاء الاصطناعي {country} {niche}",
        },
        "ja": {
            "ai_adoption": "日本 {niche} AI 導入 自動化 DX 市場 調査",
            "demand": "日本 {niche} 業務効率化 システム 需要",
            "labor": "日本 {niche} 人手不足 コスト 課題",
            "competition": "日本 {niche} AI サービス 競合 状況",
        },
        "zh": {
            "ai_adoption": "{country} {niche} 人工智能 自动化 行业应用 市场报告",
            "demand": "{country} {niche} 企业软件 数字化转型 需求",
            "labor": "{country} {niche} 用工成本 效率痛点",
            "competition": "{country} {niche} AI服务 竞争分析",
        },
        "ko": {
            "ai_adoption": "한국 {niche} AI 자동화 도입 디지털 전환 시장 보고서",
            "demand": "한국 {niche} 업무 자동화 솔루션 수요",
            "labor": "한국 {niche} 인력 부족 인건비 부담",
            "competition": "한국 {niche} AI 솔루션 경쟁 현황",
        },
        "de": {
            "ai_adoption": "Deutschland {niche} KI Automatisierung Digitalisierung Marktbericht",
            "demand": "Deutschland {niche} Softwarelösungen Nachfrage Effizienz",
            "labor": "Deutschland {niche} Fachkräftemangel Betriebskosten",
            "competition": "Deutschland {niche} KI Agenturen Wettbewerb",
        },
        "fr": {
            "ai_adoption": "France {niche} intelligence artificielle automatisation rapport de marché",
            "demand": "France {niche} logiciels solutions demande transformation digitale",
            "labor": "France {niche} pénurie de main-d'œuvre coûts opérationnels",
            "competition": "France {niche} agences IA concurrence",
        },
    }

    def get_queries(self, country_code: str, country_name: str, niche: str, lang: str = "en") -> List[str]:
        target_lang = lang if lang in self.LANGUAGE_QUERY_TEMPLATES else "en"
        templates = self.LANGUAGE_QUERY_TEMPLATES[target_lang]
        
        queries = []
        for key, tmpl in templates.items():
            q = tmpl.format(country=country_name, niche=niche.replace("-", " "))
            queries.append(q)
            
        # Always supplement non-English markets with primary English query
        if target_lang != "en":
            queries.append(f"{country_name} {niche.replace('-', ' ')} business automation AI market")

        return queries

market_localization = MarketLocalization()
