from typing import List, Dict, Any, Optional
from datetime import datetime
from app.database.models import MarketEvidence
from app.market_intelligence.models import ExtractedSignal, SignalType

class MarketSignalExtractor:
    """Extracts normalized market signals from collected empirical evidence."""

    def extract_signals_from_evidence(
        self, evidence_list: List[MarketEvidence]
    ) -> Dict[str, ExtractedSignal]:
        by_type: Dict[str, List[MarketEvidence]] = {}
        for ev in evidence_list:
            by_type.setdefault(ev.signal_type, []).append(ev)

        signals: Dict[str, ExtractedSignal] = {}

        for sig_type in SignalType:
            items = by_type.get(sig_type.value, [])
            if not items:
                # Signal is UNKNOWN - do NOT fabricate numbers
                signals[sig_type.value] = ExtractedSignal(
                    signal_type=sig_type.value,
                    value=None,
                    unit="normalized",
                    direction="NEUTRAL",
                    confidence=0.1,
                    evidence_ids=[]
                )
                continue

            # Weight evidence items by confidence
            total_weight = sum(e.confidence_score for e in items)
            if total_weight == 0:
                signals[sig_type.value] = ExtractedSignal(
                    signal_type=sig_type.value,
                    value=0.5,
                    unit="normalized",
                    direction="NEUTRAL",
                    confidence=0.1,
                    evidence_ids=[e.evidence_id for e in items]
                )
                continue

            # Compute normalized score
            # Positive claims pull towards 1.0, contradicting towards 0.0
            pos_weight = sum(e.confidence_score for e in items if e.supports_claim and not e.contradicts_claim)
            val = round(pos_weight / total_weight, 3)

            avg_conf = round(total_weight / len(items), 3)
            direction = "POSITIVE" if val >= 0.55 else ("NEGATIVE" if val <= 0.45 else "NEUTRAL")

            signals[sig_type.value] = ExtractedSignal(
                signal_type=sig_type.value,
                value=val,
                unit="normalized",
                direction=direction,
                confidence=avg_conf,
                evidence_ids=[e.evidence_id for e in items]
            )

        return signals

market_signal_extractor = MarketSignalExtractor()
