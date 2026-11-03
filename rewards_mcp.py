"""MCP server for the content rewards service (mcp SDK 2.x).

The tools work on the same in-memory stores and the same Pydantic models
as the REST API. Every tool returns a Pydantic object, so the output is
schema-valid. Run `python mcp_stdio.py` for stdio, or call `/mcp` on the
HTTP server for Streamable HTTP.
"""
from decimal import Decimal
from typing import Dict, List, Optional

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field
from starlette.applications import Starlette

from hello_rewards import (
    Attribution,
    AttributionMethod,
    ContentUnit,
    LICENSE_FACTORS,
    LICENSE_URLS,
    LicenseType,
    ModelOutput,
    RewardEvent,
    calculate_rewards,
)


class CitationInput(BaseModel):
    content_unit_id: str
    influence_score: float = Field(ge=0.0, le=1.0)
    method: AttributionMethod = AttributionMethod.EXACT_MATCH


class ContentList(BaseModel):
    count: int
    content_units: List[ContentUnit]


class Ledger(BaseModel):
    count: int
    events: List[RewardEvent]


class EarningsLine(BaseModel):
    event_id: str
    content_unit_id: str
    amount: Decimal


class ContributorEarnings(BaseModel):
    contributor_id: str
    total_earnings: Decimal
    allocations: List[EarningsLine]


class LicenseInfo(BaseModel):
    license: LicenseType
    factor: Decimal
    url: str


class LeaderboardRow(BaseModel):
    rank: int
    contributor_id: str
    earnings: Decimal
    content_units: int


class Leaderboard(BaseModel):
    pool: Decimal
    total_content_units: int
    rankings: List[LeaderboardRow]


def build_mcp(
    content_store: Dict[str, ContentUnit],
    output_store: Dict[str, ModelOutput],
    reward_events: List[RewardEvent],
) -> MCPServer:
    mcp = MCPServer(
        "sovsrc-content-rewards",
        instructions=(
            "Content rewards service. Add licensed content, record a model "
            "output with citations, then calculate rewards from a pool. "
            "The license factor scales each citation. A factor of 0 pays nothing."
        ),
    )

    @mcp.tool()
    def list_licenses() -> List[LicenseInfo]:
        """List the license types with their reward factor and license text URL."""
        return [
            LicenseInfo(license=lt, factor=LICENSE_FACTORS[lt], url=LICENSE_URLS[lt])
            for lt in LicenseType
        ]

    @mcp.tool()
    def list_content(
        license: Optional[LicenseType] = None,
        id_prefix: Optional[str] = None,
    ) -> ContentList:
        """List content units. Filter by license type or by id prefix, for example 'macbeth'."""
        units = list(content_store.values())
        if license is not None:
            units = [u for u in units if u.license == license]
        if id_prefix:
            units = [u for u in units if u.id.startswith(id_prefix)]
        return ContentList(count=len(units), content_units=units)

    @mcp.tool()
    def get_content(content_id: str) -> ContentUnit:
        """Get one content unit by id."""
        unit = content_store.get(content_id)
        if unit is None:
            raise ToolError(f"Content not found: {content_id}")
        return unit

    @mcp.tool()
    def add_content(
        text: str,
        license: LicenseType,
        contributor_id: str,
        source_uri: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> ContentUnit:
        """Add a content unit. If source_uri is empty, use the license text URL."""
        unit = ContentUnit(
            text=text,
            source_uri=source_uri or LICENSE_URLS[license],
            license=license,
            contributor_id=contributor_id,
            metadata=metadata or {},
        )
        content_store[unit.id] = unit
        return unit

    @mcp.tool()
    def record_model_output(
        prompt: str,
        response: str,
        citations: List[CitationInput],
    ) -> ModelOutput:
        """Record a model output with citations. Each citation names a content unit and an influence score from 0 to 1."""
        output = ModelOutput(
            prompt=prompt,
            response=response,
            citations=[
                Attribution(
                    content_unit_id=c.content_unit_id,
                    influence_score=c.influence_score,
                    method=c.method,
                )
                for c in citations
            ],
        )
        output_store[output.id] = output
        return output

    @mcp.tool()
    def calculate_reward_event(
        model_output_id: str,
        pool_amount: Decimal = Decimal("100"),
    ) -> RewardEvent:
        """Pay a pool for one recorded model output. Returns the reward event with one allocation per paid citation."""
        output = output_store.get(model_output_id)
        if output is None:
            raise ToolError(f"Model output not found: {model_output_id}")
        event = calculate_rewards(output, content_store, pool_amount)
        reward_events.append(event)
        return event

    @mcp.tool()
    def get_ledger() -> Ledger:
        """List all reward events."""
        return Ledger(count=len(reward_events), events=list(reward_events))

    @mcp.tool()
    def get_contributor_earnings(contributor_id: str) -> ContributorEarnings:
        """Sum the earnings of one contributor across all reward events."""
        total = Decimal("0")
        lines: List[EarningsLine] = []
        for event in reward_events:
            for alloc in event.allocations:
                if alloc.contributor_id == contributor_id:
                    total += alloc.amount
                    lines.append(EarningsLine(
                        event_id=event.id,
                        content_unit_id=alloc.content_unit_id,
                        amount=alloc.amount,
                    ))
        return ContributorEarnings(
            contributor_id=contributor_id, total_earnings=total, allocations=lines
        )

    @mcp.tool()
    def leaderboard(
        id_prefix: str = "macbeth",
        pool_amount: Decimal = Decimal("100"),
    ) -> Leaderboard:
        """Rank contributors by reward when the pool is split over all content units with the id prefix, with equal influence."""
        units = [u for u in content_store.values() if u.id.startswith(id_prefix)]
        if not units:
            return Leaderboard(pool=pool_amount, total_content_units=0, rankings=[])
        output = ModelOutput(
            prompt=f"leaderboard:{id_prefix}",
            response="",
            citations=[
                Attribution(
                    content_unit_id=u.id,
                    influence_score=1.0 / len(units),
                    method=AttributionMethod.EXACT_MATCH,
                )
                for u in units
            ],
        )
        event = calculate_rewards(output, content_store, pool_amount)
        totals: Dict[str, Decimal] = {}
        counts: Dict[str, int] = {}
        for alloc in event.allocations:
            totals[alloc.contributor_id] = totals.get(alloc.contributor_id, Decimal("0")) + alloc.amount
        for u in units:
            counts[u.contributor_id] = counts.get(u.contributor_id, 0) + 1
        ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
        return Leaderboard(
            pool=pool_amount,
            total_content_units=len(units),
            rankings=[
                LeaderboardRow(rank=i + 1, contributor_id=c, earnings=amt, content_units=counts[c])
                for i, (c, amt) in enumerate(ranked)
            ],
        )

    @mcp.resource("sovsrc://ontology")
    def ontology() -> str:
        """JSON schema of the content rewards models."""
        import json
        schemas = {
            m.__name__: m.model_json_schema()
            for m in (ContentUnit, Attribution, ModelOutput, RewardEvent)
        }
        return json.dumps(schemas, indent=2)

    return mcp


def build_http_app(mcp: MCPServer) -> Starlette:
    """Build the Streamable HTTP app. Mount it at the root of the FastAPI app, last.

    Stateless mode with JSON responses works through the Cloudflare Worker
    proxy. DNS rebinding protection is off because the server runs behind
    a public hostname, not on localhost.
    """
    return mcp.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
