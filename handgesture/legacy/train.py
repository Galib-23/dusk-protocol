import os
import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import transforms
from torchvision.datasets import ImageFolder
from torch.utils.data import DataLoader, random_split
from tqdm import tqdm

# ===========================
# Dataset Path
# ===========================

train_dir = "train/train"
test_dir = "test/test"

# ===========================
# Image Transform
# ===========================

transform = transforms.Compose([
    transforms.RandomRotation(10),
    transforms.RandomHorizontalFlip(),
    transforms.Resize((40,40)),
    transforms.ToTensor(),
    transforms.Normalize(
        [0.485,0.456,0.406],
        [0.229,0.224,0.225]
    )
])

train_dataset = ImageFolder(train_dir, transform=transform)
test_dataset = ImageFolder(test_dir, transform=transform)

print("Total Images :", len(train_dataset))
print("Classes :", train_dataset.classes)

# ===========================
# Train Validation Split
# ===========================

torch.manual_seed(10)

val_size = len(train_dataset)//5
train_size = len(train_dataset)-val_size

train_ds, val_ds = random_split(
    train_dataset,
    [train_size,val_size]
)

batch_size = 64

train_loader = DataLoader(
    train_ds,
    batch_size=batch_size,
    shuffle=True
)

val_loader = DataLoader(
    val_ds,
    batch_size=batch_size
)

test_loader = DataLoader(
    test_dataset,
    batch_size=batch_size
)

device = torch.device(
    "cuda" if torch.cuda.is_available() else "cpu"
)

print(device)

# ===========================
# Accuracy Function
# ===========================

def accuracy(outputs, labels):
    _, preds = torch.max(outputs, dim=1)
    return (preds == labels).float().mean()


# ===========================
# Base Model
# ===========================

class ImageClassificationBase(nn.Module):

    def training_step(self, batch):
        images, labels = batch
        images = images.to(device)
        labels = labels.to(device)

        out = self(images)
        loss = F.cross_entropy(out, labels)

        return loss

    def validation_step(self, batch):
        images, labels = batch
        images = images.to(device)
        labels = labels.to(device)

        out = self(images)

        loss = F.cross_entropy(out, labels)
        acc = accuracy(out, labels)

        return {
            "val_loss": loss.detach(),
            "val_acc": acc.detach()
        }

    def validation_epoch_end(self, outputs):

        losses = torch.stack([x["val_loss"] for x in outputs]).mean()

        accs = torch.stack([x["val_acc"] for x in outputs]).mean()

        return {
            "val_loss": losses.item(),
            "val_acc": accs.item()
        }

    def epoch_end(self, epoch, result):

        print(
            f"Epoch [{epoch+1}] "
            f"Train Loss: {result['train_loss']:.4f} | "
            f"Val Loss: {result['val_loss']:.4f} | "
            f"Val Acc: {result['val_acc']:.4f}"
        )

        # ===========================
# CNN Model
# ===========================

class CnnModel(ImageClassificationBase):

    def __init__(self):
        super().__init__()

        self.network = nn.Sequential(

            nn.Conv2d(3,100,kernel_size=3,padding=1),
            nn.ReLU(),

            nn.Conv2d(100,150,kernel_size=3,padding=1),
            nn.ReLU(),

            nn.MaxPool2d(2,2),

            nn.Conv2d(150,200,kernel_size=3,padding=1),
            nn.ReLU(),

            nn.Conv2d(200,200,kernel_size=3,padding=1),
            nn.ReLU(),

            nn.MaxPool2d(2,2),

            nn.Conv2d(200,250,kernel_size=3,padding=1),
            nn.ReLU(),

            nn.Conv2d(250,250,kernel_size=3,padding=1),
            nn.ReLU(),

            nn.MaxPool2d(2,2),

            nn.Flatten(),

            nn.Linear(6250,256),
            nn.ReLU(),

            nn.Linear(256,128),
            nn.ReLU(),

            nn.Linear(128,64),
            nn.ReLU(),

            nn.Linear(64,32),
            nn.ReLU(),

            nn.Dropout(0.25),

            nn.Linear(32,len(train_dataset.classes))
        )

    def forward(self,x):
        return self.network(x)


# ===========================
# Create Model
# ===========================

model = CnnModel().to(device)

print(model)


# ===========================
# Validation Function
# ===========================

@torch.no_grad()
def evaluate(model, loader):

    model.eval()

    outputs = []

    for batch in loader:
        outputs.append(model.validation_step(batch))

    return model.validation_epoch_end(outputs)


# ===========================
# Training Function
# ===========================

def fit(epochs, lr, model, train_loader, val_loader):

    history = []

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    for epoch in range(epochs):

        model.train()

        train_losses = []

        for images, labels in tqdm(train_loader):

            images = images.to(device)
            labels = labels.to(device)

            out = model(images)

            loss = F.cross_entropy(out, labels)

            train_losses.append(loss.detach())

            loss.backward()

            optimizer.step()

            optimizer.zero_grad()

        result = evaluate(model, val_loader)

        result["train_loss"] = torch.stack(train_losses).mean().item()

        model.epoch_end(epoch, result)

        history.append(result)

    return history


# ===========================
# Train Model
# ===========================

num_epochs = 10
learning_rate = 0.001

print("Training Started...\n")

history = fit(
    num_epochs,
    learning_rate,
    model,
    train_loader,
    val_loader
)

# ===========================
# Test Accuracy
# ===========================

from sklearn.metrics import classification_report

print("\nEvaluating on Test Dataset...\n")

result = evaluate(model, test_loader)

print(result)

# ===========================
# Classification Report
# ===========================

model.eval()

predictions = []
true_labels = []

with torch.no_grad():

    for images, labels in test_loader:

        images = images.to(device)

        outputs = model(images)

        _, preds = torch.max(outputs, 1)

        predictions.extend(preds.cpu().numpy())

        true_labels.extend(labels.numpy())

print(classification_report(
    true_labels,
    predictions,
    target_names=train_dataset.classes
))

# ===========================
# Save Model
# ===========================

torch.save(model.state_dict(), "gesture_model.pth")

print("\nModel Saved Successfully!")
print("File Name : gesture_model.pth")