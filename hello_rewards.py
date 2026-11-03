from decimal import Decimal
from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict


class LicenseType(str, Enum):
    SOVSRC_REWARDS_V1 = "sovsrc-rewards-v1"
    CC_BY_4_0 = "cc-by-4.0"
    PROPRIETARY_OPT_IN = "proprietary-opt-in"
    PUBLIC_DOMAIN = "public-domain"


class AttributionMethod(str, Enum):
    EXACT_MATCH = "exact_match"
    SEMANTIC_SIMILARITY = "semantic_similarity"
    INFERENCE_TRACE = "inference_trace"


class ContentUnit(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    text: str
    source_uri: str
    license: LicenseType
    contributor_id: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Attribution(BaseModel):
    model_config = ConfigDict(frozen=True)

    content_unit_id: str
    influence_score: float = Field(ge=0.0, le=1.0)
    method: AttributionMethod


class ModelOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    prompt: str
    response: str
    citations: List[Attribution] = Field(default_factory=list)
    model_version: str = "hello-rewards-0.1.0"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Allocation(BaseModel):
    model_config = ConfigDict(frozen=True)

    content_unit_id: str
    contributor_id: str
    share: Decimal
    amount: Decimal


class RewardEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    model_output_id: str
    pool_amount: Decimal
    allocations: List[Allocation]
    calculated_at: datetime = Field(default_factory=datetime.utcnow)


LICENSE_FACTORS: Dict[LicenseType, Decimal] = {
    LicenseType.SOVSRC_REWARDS_V1: Decimal("1.0"),
    LicenseType.CC_BY_4_0: Decimal("0.1"),
    LicenseType.PROPRIETARY_OPT_IN: Decimal("0.5"),
    LicenseType.PUBLIC_DOMAIN: Decimal("0.0"),
}

LICENSE_URLS: Dict[LicenseType, str] = {
    LicenseType.SOVSRC_REWARDS_V1: "https://github.com/niccolox/sovsrc.llm/blob/main/licenses/SS-SIP-0.1.md",
    LicenseType.CC_BY_4_0: "https://creativecommons.org/licenses/by/4.0/",
    LicenseType.PROPRIETARY_OPT_IN: "https://github.com/niccolox/sovsrc.llm/blob/main/licenses/PROPRIETARY_OPT_IN.md",
    LicenseType.PUBLIC_DOMAIN: "https://creativecommons.org/publicdomain/zero/1.0/",
}


def calculate_rewards(
    model_output: ModelOutput,
    content_units: Dict[str, ContentUnit],
    pool_amount: Decimal,
) -> RewardEvent:
    weighted_allocations: List[tuple[ContentUnit, Decimal]] = []
    total_weight = Decimal("0")

    for citation in model_output.citations:
        unit = content_units.get(citation.content_unit_id)
        if not unit:
            continue

        factor = LICENSE_FACTORS.get(unit.license, Decimal("0"))
        if factor == Decimal("0"):
            continue

        weight = Decimal(str(citation.influence_score)) * factor
        total_weight += weight
        weighted_allocations.append((unit, weight))

    allocations: List[Allocation] = []
    if total_weight > Decimal("0"):
        for unit, weight in weighted_allocations:
            amount = (weight / total_weight) * pool_amount
            allocations.append(
                Allocation(
                    content_unit_id=unit.id,
                    contributor_id=unit.contributor_id,
                    share=weight,
                    amount=amount,
                )
            )

    return RewardEvent(
        model_output_id=model_output.id,
        pool_amount=pool_amount,
        allocations=allocations,
    )


def main() -> None:
    print("🏁 Sovereign Source Content Rewards — Hello World")
    print("=" * 55)

    units = [
        ContentUnit(
            id="c1",
            text="The speed of light is 299,792,458 m/s",
            source_uri=LICENSE_URLS[LicenseType.SOVSRC_REWARDS_V1],
            license=LicenseType.SOVSRC_REWARDS_V1,
            contributor_id="alice",
        ),
        ContentUnit(
            id="c2",
            text="Water boils at 100°C at sea level",
            source_uri=LICENSE_URLS[LicenseType.CC_BY_4_0],
            license=LicenseType.CC_BY_4_0,
            contributor_id="bob",
        ),
        ContentUnit(
            id="c3",
            text="Proprietary research: new catalyst increases yield 12%",
            source_uri=LICENSE_URLS[LicenseType.PROPRIETARY_OPT_IN],
            license=LicenseType.PROPRIETARY_OPT_IN,
            contributor_id="corp_x",
        ),
    ]
    content_index = {u.id: u for u in units}

    print("\n📚 Content Units:")
    for u in units:
        factor = LICENSE_FACTORS[u.license]
        print(f"  {u.id} | {u.license.value:20s} | factor={factor} | contributor={u.contributor_id}")
        print(f"    \"{u.text[:60]}...\"")

    output = ModelOutput(
        id="out-1",
        prompt="What is the speed of light and boiling point of water?",
        response="Light travels at 299,792,458 m/s. Water boils at 100°C.",
        citations=[
            Attribution(
                content_unit_id="c1",
                influence_score=0.6,
                method=AttributionMethod.EXACT_MATCH,
            ),
            Attribution(
                content_unit_id="c2",
                influence_score=0.4,
                method=AttributionMethod.EXACT_MATCH,
            ),
        ],
    )

    print(f"\n🤖 Model Output: {output.id}")
    print(f"  Prompt: {output.prompt}")
    print(f"  Response: {output.response}")
    print("  Citations:")
    for c in output.citations:
        print(f"    {c.content_unit_id} | influence={c.influence_score} | method={c.method.value}")

    pool = Decimal("100")
    event = calculate_rewards(output, content_index, pool)

    print(f"\n💰 Reward Event: {event.id}")
    print(f"  Pool: {pool} tokens")
    print("  Allocations:")
    total_allocated = Decimal("0")
    for a in event.allocations:
        unit = content_index[a.content_unit_id]
        print(f"    {a.content_unit_id} ({unit.contributor_id}) | share={a.share:.4f} | amount={a.amount:.2f}")
        total_allocated += a.amount

    remainder = pool - total_allocated
    print(f"  Total allocated: {total_allocated:.2f}")
    print(f"  Remainder (burn/rollover): {remainder:.2f}")

    print("\n✅ Hello world complete — Content Rewards working!")


if __name__ == "__main__":
    main()