import torch
import lightning as L
from lightning.pytorch import LightningModule, Trainer

print(f"PyTorch: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"CUDA version: {torch.version.cuda}")
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")

class HelloModel(LightningModule):
    def __init__(self):
        super().__init__()
        self.layer = torch.nn.Linear(10, 1)

    def forward(self, x):
        return self.layer(x)

    def training_step(self, batch, batch_idx):
        x, y = batch
        y_hat = self(x)
        loss = torch.nn.functional.mse_loss(y_hat, y)
        self.log("train_loss", loss)
        return loss

    def configure_optimizers(self):
        return torch.optim.Adam(self.parameters(), lr=0.01)

    def train_dataloader(self):
        dataset = torch.utils.data.TensorDataset(
            torch.randn(100, 10),
            torch.randn(100, 1)
        )
        return torch.utils.data.DataLoader(dataset, batch_size=16)

model = HelloModel()
trainer = Trainer(max_epochs=1, accelerator="auto", devices="auto", logger=False, enable_checkpointing=False)
trainer.fit(model)

print("\n✅ Hello world complete — Lightning + CUDA working!")