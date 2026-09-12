"""
Simplified, clean Unidirectional LSTM architecture for causal attack forecasting.
"""

import torch
import torch.nn as nn


class AttackLSTM(nn.Module):
    """
    Compact Unidirectional PyTorch LSTM for causal network attack forecasting.

    Structure:
    Input [B, S, F]
    -> LayerNorm(F)
    -> 1 or 2-layer Unidirectional LSTM(F, hidden_size)
    -> Last time-step hidden state h_S [B, hidden_size]
    -> Linear head [B, hidden_size] -> Dropout -> GELU -> Linear [B, 1]
    """
    def __init__(
        self,
        input_dim: int = 15,
        hidden_size: int = 64,
        num_layers: int = 1,
        dropout: float = 0.2,
    ):
        super().__init__()
        self.input_dim = input_dim
        self.hidden_size = hidden_size
        self.num_layers = num_layers

        # Input feature normalization across sequence steps
        self.input_norm = nn.LayerNorm(input_dim)

        # Unidirectional LSTM (causal forward processing)
        self.lstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
            bidirectional=False,
        )

        # Dense Classification Head
        self.head = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(hidden_size, 32),
            nn.GELU(),
            nn.Dropout(dropout * 0.5),
            nn.Linear(32, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        x shape: [batch_size, sequence_length, feature_dim]
        returns logits shape: [batch_size, 1]
        """
        # Apply layer normalization across input features
        x_norm = self.input_norm(x)

        # LSTM forward pass
        lstm_out, (h_n, c_n) = self.lstm(x_norm)

        # Extract last time step output: [batch_size, hidden_size]
        last_step = lstm_out[:, -1, :]

        # Output logits
        logits = self.head(last_step).squeeze(-1)
        return logits

    def predict_proba(self, x: torch.Tensor) -> torch.Tensor:
        """Helper to get probability scores via Sigmoid."""
        self.eval()
        with torch.no_grad():
            logits = self.forward(x)
            return torch.sigmoid(logits)
