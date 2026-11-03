from decimal import Decimal
from typing import Dict, List, Optional
from contextlib import asynccontextmanager
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, ConfigDict

from hello_rewards import (
    ContentUnit,
    Attribution,
    ModelOutput,
    LicenseType,
    AttributionMethod,
    LICENSE_FACTORS,
    LICENSE_URLS,
    calculate_rewards,
    RewardEvent,
    Allocation,
)

import torch
from torch.utils.data import TensorDataset, DataLoader
import lightning as L
from lightning.pytorch import LightningModule, Trainer

from rewards_mcp import build_mcp, build_http_app

# Jinja2 setup
from jinja2 import Environment, FileSystemLoader
template_env = Environment(loader=FileSystemLoader("templates"))


content_store: Dict[str, ContentUnit] = {}
output_store: Dict[str, ModelOutput] = {}
reward_events: List[RewardEvent] = []


def seed_content() -> None:
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
    for u in units:
        content_store[u.id] = u


def seed_macbeth() -> None:
    candidates = [
        Path(__file__).parent / "macbeth.json",
        Path(__file__).parent.parent / "macbeth.json",
    ]
    macbeth_path = next((p for p in candidates if p.exists()), None)
    if macbeth_path is None:
        print(f"Macbeth file not found in {[str(p) for p in candidates]}")
        return

    with open(macbeth_path) as f:
        data = json.load(f)

    speech_id = 1
    for character in data["characters"]:
        contributor_id = character["name"].lower().replace("'", "").replace(" ", "_")
        for speech in character["key_speeches"]:
            license_str = speech["license"]
            try:
                license_type = LicenseType(license_str)
            except ValueError:
                license_type = LicenseType.PUBLIC_DOMAIN

            unit = ContentUnit(
                id=f"macbeth-speech-{speech_id}",
                text=speech["line"],
                source_uri=LICENSE_URLS[license_type],
                license=license_type,
                contributor_id=contributor_id,
                metadata={
                    "play": data["play"],
                    "act": speech["act"],
                    "context": speech["context"],
                    "character": character["name"],
                },
            )
            content_store[unit.id] = unit
            speech_id += 1

    print(f"Seeded {speech_id - 1} Macbeth speeches from {len(data['characters'])} characters")


# Seed content at module level (runs on import)
seed_content()
seed_macbeth()


# MCP server on the same stores and models. Mounted at /mcp below.
mcp = build_mcp(content_store, output_store, reward_events)
mcp_http_app = build_http_app(mcp)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="Sovereign Source Content Rewards API",
    version="0.1.0",
    lifespan=lifespan,
)


class ContentIngestRequest(BaseModel):
    text: str
    source_uri: str
    license: LicenseType
    contributor_id: str
    metadata: Dict = Field(default_factory=dict)


class AttributeRequest(BaseModel):
    prompt: str
    response: str
    citations: List[Dict]


class RewardRequest(BaseModel):
    model_output_id: str
    pool_amount: Decimal = Decimal("100")


@app.get("/")
async def root():
    return {
        "name": "Sovereign Source Content Rewards API",
        "version": "0.1.0",
        "endpoints": [
            "GET /content",
            "POST /content",
            "POST /attribute",
            "POST /rewards/calculate",
            "GET /rewards/ledger",
            "GET /contributors/{contributor_id}/earnings",
            "GET /demo/hello-world",
        ],
    }


@app.get("/content")
async def list_content(
    license: Optional[str] = Query(None, description="Filter by license type"),
    filter: Optional[str] = Query(None, description="Filter by prefix (e.g., 'macbeth')"),
):
    units = list(content_store.values())
    
    if license:
        units = [u for u in units if u.license.value == license]
    if filter:
        units = [u for u in units if u.id.startswith(filter)]
    
    return {"content_units": units}


# HTMX UI Routes
@app.get("/ui", response_class=HTMLResponse)
async def ui_dashboard(request: Request):
    # Calculate stats
    total = len(content_store)
    license_dist = {}
    for u in content_store.values():
        license_dist[u.license.value] = license_dist.get(u.license.value, 0) + 1
    
    template = template_env.get_template("dashboard.html")
    return HTMLResponse(template.render(
        request=request, total_content=total, license_distribution=license_dist
    ))


@app.get("/ui/content", response_class=HTMLResponse)
async def ui_content(request: Request):
    template = template_env.get_template("content.html")
    return HTMLResponse(template.render(request=request))


@app.get("/ui/attribute", response_class=HTMLResponse)
async def ui_attribute(request: Request):
    template = template_env.get_template("attribute.html")
    return HTMLResponse(template.render(request=request))


@app.get("/ui/rewards", response_class=HTMLResponse)
async def ui_rewards(request: Request):
    template = template_env.get_template("rewards.html")
    return HTMLResponse(template.render(request=request))


@app.get("/ui/demo", response_class=HTMLResponse)
async def ui_demo(request: Request):
    template = template_env.get_template("demo.html")
    return HTMLResponse(template.render(request=request))


@app.get("/ui/leaderboard", response_class=HTMLResponse)
async def ui_leaderboard(request: Request):
    template = template_env.get_template("leaderboard.html")
    return HTMLResponse(template.render(request=request))


# README page: the ontology section is built from the Pydantic models, so
# the page cannot drift from the code.
def _type_name(annotation) -> str:
    if isinstance(annotation, type):
        return annotation.__name__
    text = str(annotation)
    for prefix in ("typing.", "hello_rewards.", "server.", "__main__.", "torch."):
        text = text.replace(prefix, "")
    return text


def describe_model(model_cls) -> Dict:
    fields = []
    for name, field in model_cls.model_fields.items():
        constraints = []
        for meta in field.metadata:
            for attr in ("ge", "gt", "le", "lt", "min_length", "max_length"):
                value = getattr(meta, attr, None)
                if value is not None:
                    constraints.append(f"{attr}={value}")
        if field.is_required():
            default = "required"
        elif field.default_factory is not None:
            default = "generated"
        else:
            default = repr(field.default)
        fields.append({
            "name": name,
            "type": _type_name(field.annotation),
            "default": default,
            "constraints": ", ".join(constraints),
        })
    bases = [b.__name__ for b in model_cls.__bases__ if b is not BaseModel]
    return {
        "name": model_cls.__name__,
        "doc": (model_cls.__doc__ or "").strip(),
        "frozen": bool(model_cls.model_config.get("frozen")),
        "bases": bases,
        "fields": fields,
    }


def describe_enum(enum_cls) -> Dict:
    return {
        "name": enum_cls.__name__,
        "members": [{"name": m.name, "value": m.value} for m in enum_cls],
    }


@app.get("/ui/readme", response_class=HTMLResponse)
async def ui_readme(request: Request):
    models = [
        describe_model(m)
        for m in (ContentUnit, TrainingContentUnit, Attribution, ModelOutput, Allocation, RewardEvent)
    ]
    enums = [describe_enum(LicenseType), describe_enum(AttributionMethod)]
    licenses = [
        {"license": lt.value, "factor": str(LICENSE_FACTORS[lt]), "url": LICENSE_URLS[lt]}
        for lt in LicenseType
    ]
    template = template_env.get_template("readme.html")
    return HTMLResponse(template.render(
        request=request, models=models, enums=enums, licenses=licenses,
    ))


# Leaderboard API Endpoints
@app.get("/leaderboard/macbeth")
async def leaderboard_macbeth(pool: Decimal = Decimal("100")):
    """Calculate leaderboard for Macbeth speeches with equal attribution."""
    from hello_rewards import ModelOutput, Attribution, AttributionMethod
    
    macbeth_units = [u for u in content_store.values() if u.id.startswith("macbeth")]
    
    # Create a model output citing all Macbeth speeches equally
    citations = []
    for unit in macbeth_units:
        citations.append(Attribution(
            content_unit_id=unit.id,
            influence_score=1.0 / len(macbeth_units),
            method=AttributionMethod.EXACT_MATCH,
        ))
    
    output = ModelOutput(
        prompt="Rank all Macbeth speeches by reward value",
        response="All Macbeth speeches attributed equally",
        citations=citations,
    )
    
    event = calculate_rewards(output, content_store, pool)
    
    # Aggregate by contributor
    contributor_totals = {}
    for alloc in event.allocations:
        contributor_totals[alloc.contributor_id] = contributor_totals.get(alloc.contributor_id, Decimal("0")) + alloc.amount
    
    # Sort by earnings
    ranked = sorted(contributor_totals.items(), key=lambda x: -x[1])
    
    return {
        "pool": str(pool),
        "total_speeches": len(macbeth_units),
        "rankings": [
            {"rank": i + 1, "contributor": c, "earnings": str(amt), "speeches": sum(1 for u in macbeth_units if u.contributor_id == c)}
            for i, (c, amt) in enumerate(ranked)
        ],
    }


@app.get("/leaderboard/macbeth/values")
async def leaderboard_macbeth_values(pool: Decimal = Decimal("100")):
    """Show individual speech values."""
    from hello_rewards import ModelOutput, Attribution, AttributionMethod
    
    macbeth_units = [u for u in content_store.values() if u.id.startswith("macbeth")]
    
    speech_values = []
    for unit in macbeth_units:
        # Calculate value if this speech gets 100% attribution
        citations = [Attribution(
            content_unit_id=unit.id,
            influence_score=1.0,
            method=AttributionMethod.EXACT_MATCH,
        )]
        output = ModelOutput(
            prompt=f"Value of {unit.id}",
            response=unit.text,
            citations=citations,
        )
        event = calculate_rewards(output, content_store, pool)
        total = sum(a.amount for a in event.allocations)
        speech_values.append({
            "id": unit.id,
            "character": unit.metadata.get("character"),
            "act": unit.metadata.get("act"),
            "license": unit.license.value,
            "text_preview": unit.text[:80],
            "full_value": str(total),
        })
    
    # Sort by value descending
    speech_values.sort(key=lambda x: Decimal(x["full_value"]), reverse=True)
    
    return {
        "pool": str(pool),
        "speeches": speech_values,
    }


@app.get("/leaderboard/macbeth/characters")
async def leaderboard_macbeth_characters(pool: Decimal = Decimal("100")):
    """Show character-level earnings."""
    from hello_rewards import ModelOutput, Attribution, AttributionMethod
    
    macbeth_units = [u for u in content_store.values() if u.id.startswith("macbeth")]
    
    # Group by character
    char_totals = {}
    for unit in macbeth_units:
        citations = [Attribution(
            content_unit_id=unit.id,
            influence_score=1.0,
            method=AttributionMethod.EXACT_MATCH,
        )]
        output = ModelOutput(
            prompt=f"Value of {unit.id}",
            response=unit.text,
            citations=citations,
        )
        event = calculate_rewards(output, content_store, pool)
        total = sum(a.amount for a in event.allocations)
        
        char = unit.metadata.get("character", unit.contributor_id)
        char_totals[char] = char_totals.get(char, Decimal("0")) + total
    
    ranked = sorted(char_totals.items(), key=lambda x: -x[1])
    
    return {
        "pool": str(pool),
        "characters": [
            {"rank": i + 1, "character": c, "total_value": str(amt), "speech_count": sum(1 for u in macbeth_units if u.metadata.get("character") == c)}
            for i, (c, amt) in enumerate(ranked)
        ],
    }


@app.post("/content", status_code=201)
async def create_content(req: ContentIngestRequest):
    unit = ContentUnit(
        text=req.text,
        source_uri=req.source_uri,
        license=req.license,
        contributor_id=req.contributor_id,
        metadata=req.metadata,
    )
    content_store[unit.id] = unit
    return unit


@app.get("/content/{content_id}")
async def get_content(content_id: str):
    if content_id not in content_store:
        raise HTTPException(status_code=404, detail="Content not found")
    return content_store[content_id]


@app.post("/attribute")
async def attribute_output(req: AttributeRequest):
    citations = [
        Attribution(
            content_unit_id=c["content_unit_id"],
            influence_score=c["influence_score"],
            method=AttributionMethod(c["method"]),
        )
        for c in req.citations
    ]
    output = ModelOutput(
        prompt=req.prompt,
        response=req.response,
        citations=citations,
    )
    output_store[output.id] = output
    return output


@app.post("/rewards/calculate")
async def calculate_reward(req: RewardRequest):
    if req.model_output_id not in output_store:
        raise HTTPException(status_code=404, detail="Model output not found")

    output = output_store[req.model_output_id]
    event = calculate_rewards(output, content_store, req.pool_amount)
    reward_events.append(event)
    return event


@app.get("/rewards/ledger")
async def get_ledger():
    return {"events": reward_events}


@app.get("/contributors/{contributor_id}/earnings")
async def get_contributor_earnings(contributor_id: str):
    earnings = Decimal("0")
    allocations = []
    for event in reward_events:
        for alloc in event.allocations:
            if alloc.contributor_id == contributor_id:
                earnings += alloc.amount
                allocations.append({
                    "event_id": event.id,
                    "content_unit_id": alloc.content_unit_id,
                    "amount": str(alloc.amount),
                })
    return {
        "contributor_id": contributor_id,
        "total_earnings": str(earnings),
        "allocations": allocations,
    }


@app.get("/demo/hello-world")
async def demo_hello_world():
    output = ModelOutput(
        id="demo-out-1",
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
    event = calculate_rewards(output, content_store, Decimal("100"))
    reward_events.append(event)
    return {
        "model_output": output,
        "reward_event": event,
        "summary": {
            "pool": "100 tokens",
            "allocations": [
                {"contributor": "alice", "amount": "93.75", "license": "sovsrc-rewards-v1"},
                {"contributor": "bob", "amount": "6.25", "license": "cc-by-4.0"},
            ],
            "remainder": "0.00",
        },
    }


class TrainingContentUnit(ContentUnit):
    tensor_x: torch.Tensor
    tensor_y: torch.Tensor

    model_config = ConfigDict(arbitrary_types_allowed=True)


class RewardsHelloModel(LightningModule):
    def __init__(self, content_units: List[TrainingContentUnit]):
        super().__init__()
        self.layer = torch.nn.Linear(10, 1)
        self.content_units = content_units
        self.content_index = {u.id: u for u in content_units}
        self.reward_events: List[RewardEvent] = []
        self.epoch_attributions: List[Attribution] = []

    def forward(self, x):
        return self.layer(x)

    def training_step(self, batch, batch_idx):
        x, y = batch
        y_hat = self(x)
        loss = torch.nn.functional.mse_loss(y_hat, y)
        self.log("train_loss", loss)

        batch_size = x.size(0)
        for i in range(batch_size):
            sample_idx = batch_idx * batch_size + i
            if sample_idx < len(self.content_units):
                unit = self.content_units[sample_idx]
                self.epoch_attributions.append(Attribution(
                    content_unit_id=unit.id,
                    influence_score=1.0 / batch_size,
                    method=AttributionMethod.EXACT_MATCH,
                ))

        return loss

    def on_train_epoch_end(self):
        agg: Dict[str, float] = {}
        for attr in self.epoch_attributions:
            agg[attr.content_unit_id] = agg.get(attr.content_unit_id, 0) + attr.influence_score

        citations = [
            Attribution(content_unit_id=uid, influence_score=score, method=AttributionMethod.EXACT_MATCH)
            for uid, score in agg.items()
        ]

        output = ModelOutput(
            prompt=f"Train epoch {self.current_epoch}",
            response=f"Completed epoch with {len(citations)} attributed samples",
            citations=citations,
        )

        pool = Decimal("1000")
        event = calculate_rewards(output, self.content_index, pool)
        self.reward_events.append(event)

        self.epoch_attributions.clear()

    def configure_optimizers(self):
        return torch.optim.Adam(self.parameters(), lr=0.01)

    def train_dataloader(self):
        dataset = TensorDataset(
            torch.stack([u.tensor_x for u in self.content_units]),
            torch.stack([u.tensor_y for u in self.content_units]),
        )
        return DataLoader(dataset, batch_size=16, shuffle=True)


@app.get("/demo/unified")
async def demo_unified():
    torch.manual_seed(42)
    content_units = []
    for i in range(100):
        x = torch.randn(10)
        y = torch.randn(1)
        license_type = [
            LicenseType.SOVSRC_REWARDS_V1,
            LicenseType.CC_BY_4_0,
            LicenseType.PROPRIETARY_OPT_IN,
        ][i % 3]
        contributor = f"contributor-{i % 5}"

        content_units.append(TrainingContentUnit(
            id=f"sample-{i}",
            text=f"Training sample {i}",
            source_uri=LICENSE_URLS[license_type],
            license=license_type,
            contributor_id=contributor,
            tensor_x=x,
            tensor_y=y,
        ))

    content_index = {u.id: u for u in content_units}

    license_counts = {}
    for u in content_units:
        license_counts[u.license.value] = license_counts.get(u.license.value, 0) + 1

    model = RewardsHelloModel(content_units)
    trainer = Trainer(
        max_epochs=3,
        accelerator="auto",
        devices="auto",
        logger=False,
        enable_checkpointing=False,
        enable_progress_bar=False,
    )

    trainer.fit(model)

    total_by_contributor = {}
    for event in model.reward_events:
        for alloc in event.allocations:
            total_by_contributor[alloc.contributor_id] = (
                total_by_contributor.get(alloc.contributor_id, Decimal("0")) + alloc.amount
            )

    epoch_summaries = []
    for i, event in enumerate(model.reward_events):
        epoch_summaries.append({
            "epoch": i,
            "allocations": [
                {
                    "contributor": model.content_index[alloc.content_unit_id].contributor_id,
                    "amount": str(alloc.amount),
                    "license": model.content_index[alloc.content_unit_id].license.value,
                }
                for alloc in event.allocations
            ],
        })

    return {
        "training_content": {
            "total_samples": len(content_units),
            "license_distribution": license_counts,
        },
        "epochs": epoch_summaries,
        "final_totals": {
            contributor: str(total)
            for contributor, total in sorted(total_by_contributor.items(), key=lambda x: -x[1])
        },
    }


# Mount the MCP app last. It owns only the /mcp path. A mount at /mcp with
# an inner root path would answer POST /mcp with a redirect to /mcp/.
app.mount("/", mcp_http_app)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)