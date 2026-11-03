"""
Sovereign Source Unified Hello World
Training + Content Rewards in one run.
"""

import torch
from torch.utils.data import TensorDataset, DataLoader
import lightning as L
from lightning.pytorch import LightningModule, Trainer
from decimal import Decimal
from typing import List, Dict
from pydantic import ConfigDict

from hello_rewards import (
    ContentUnit,
    LicenseType,
    Attribution,
    AttributionMethod,
    ModelOutput,
    RewardEvent,
    calculate_rewards,
    LICENSE_FACTORS,
    LICENSE_URLS,
)


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

        print(f"\n📊 Epoch {self.current_epoch} Rewards:")
        for alloc in event.allocations:
            unit = self.content_index[alloc.content_unit_id]
            print(f"  {unit.contributor_id:15s} | {alloc.amount:>8.2f} | {unit.license.value}")

        self.epoch_attributions.clear()

    def configure_optimizers(self):
        return torch.optim.Adam(self.parameters(), lr=0.01)

    def train_dataloader(self):
        dataset = TensorDataset(
            torch.stack([u.tensor_x for u in self.content_units]),
            torch.stack([u.tensor_y for u in self.content_units]),
        )
        return DataLoader(dataset, batch_size=16, shuffle=True)


def main():
    print("🏁 Sovereign Source Unified Hello World — Training + Rewards")
    print("=" * 65)

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

    license_counts = {}
    for u in content_units:
        license_counts[u.license.value] = license_counts.get(u.license.value, 0) + 1
    print("\n📚 Training Content License Distribution:")
    for lic, count in license_counts.items():
        factor = LICENSE_FACTORS[LicenseType(lic)]
        print(f"  {lic:20s} | {count:3d} samples | factor={factor}")

    model = RewardsHelloModel(content_units)
    trainer = Trainer(
        max_epochs=3,
        accelerator="auto",
        devices="auto",
        logger=False,
        enable_checkpointing=False,
        enable_progress_bar=True,
    )

    print("\n🚀 Starting training...")
    trainer.fit(model)

    print("\n💰 Final Reward Summary:")
    total_by_contributor = {}
    for event in model.reward_events:
        for alloc in event.allocations:
            total_by_contributor[alloc.contributor_id] = (
                total_by_contributor.get(alloc.contributor_id, Decimal("0")) + alloc.amount
            )

    for contributor, total in sorted(total_by_contributor.items(), key=lambda x: -x[1]):
        print(f"  {contributor:15s} | {total:>10.2f} tokens")

    print(f"\n✅ Unified hello world complete — Training + Rewards working!")


if __name__ == "__main__":
    main()