#!/usr/bin/env python3
"""Cross-Design Generalization Evaluation"""

import os, sys, json
import torch
import torch.nn as nn
from torch_geometric.nn import SAGEConv
from torch_geometric.data import DataLoader
from blif_to_pyg import BlifToAIG

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BLIF_DIR = os.path.join(SCRIPT_DIR, 'blifs')
MODEL_DIR = os.path.join(SCRIPT_DIR, 'data', 'models')
DATA_PATH = os.path.join(SCRIPT_DIR, 'data', 'training_data.pt')


class SAGE3(nn.Module):
    def __init__(self, in_channels=10, hidden_channels=128, dropout=0.3):
        super().__init__()
        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, hidden_channels)
        self.conv3 = SAGEConv(hidden_channels, hidden_channels // 2)
        self.mlp = nn.Sequential(
            nn.Linear(hidden_channels // 2, 32), nn.ReLU(),
            nn.Dropout(dropout), nn.Linear(32, 1),
        )
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index).relu(); x = self.dropout(x)
        x = self.conv2(x, edge_index).relu(); x = self.dropout(x)
        x = self.conv3(x, edge_index).relu(); x = self.dropout(x)
        return torch.sigmoid(self.mlp(x).squeeze(-1))


def compute_metrics(scores, labels, threshold=0.5):
    from sklearn.metrics import f1_score, precision_score, recall_score, accuracy_score
    from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
    from scipy.stats import pearsonr
    preds = (scores >= threshold).float()
    binary_labels = (labels >= threshold).float()
    r2 = r2_score(labels.numpy(), scores.numpy())
    corr, _ = pearsonr(labels.numpy(), scores.numpy())
    return {
        'f1': f1_score(binary_labels.numpy(), preds.numpy(), zero_division=0),
        'precision': precision_score(binary_labels.numpy(), preds.numpy(), zero_division=0),
        'recall': recall_score(binary_labels.numpy(), preds.numpy(), zero_division=0),
        'accuracy': accuracy_score(binary_labels.numpy(), preds.numpy()),
        'mse': mean_squared_error(labels.numpy(), scores.numpy()),
        'mae': mean_absolute_error(labels.numpy(), scores.numpy()),
        'r2': r2,
        'corr': corr,
    }


BLIF_CATEGORIES = {
    'counter': [
        'output_counter.blif',
        'output_cnt_comp_mod.blif',
        'output_cnt_comp_down.blif',
        'output_cnt_comp_up.blif',
    ],
    'ecc': [
        'output_ecc_register.blif',
        'output_ecc_bus.blif',
        'output_ecc_encoder.blif',
        'output_ecc_decoder.blif',
        'output_ecc_register_dft.blif',
        'output_mixed_design_ecc.blif',
    ],
    'parity': [
        'output_parity_byte.blif',
        'output_parity_bus.blif',
        'output_parity_check.blif',
        'output_parity_gen.blif',
        'output_parity_register.blif',
    ],
    'dice_tmr': [
        'output_dice_register.blif',
        'output_dice_ff.blif',
        'output_dice_tmr_register.blif',
        'output_tmr_voter_6ch_xilinx.blif',
        'output_tmr_voter_6ch_pipeline.blif',
    ],
    'cpu': [
        'output_rv32i_cpu_core.blif',
        'output_pipeline_cpu.blif',
    ],
    'other': [
        'output_fir_filter_bank.blif',
        'output_systolic_array.blif',
    ],
}


def load_blif_data(blif_files):
    data_list = []
    for blif_name in blif_files:
        blif_path = os.path.join(BLIF_DIR, blif_name)
        if not os.path.exists(blif_path):
            continue
        try:
            converter = BlifToAIG(blif_path)
            base_data = converter.build_pyg_data()
            if base_data is None or base_data.x is None or len(base_data.x) == 0:
                continue
            label = converter.generate_fault_labels(
                deterministic=True,
                label_mode='prob_decay',
                fault_targets=(converter.PI, converter.AND, converter.DFF),
            )
            for _ in range(8):
                data = base_data.clone()
                data.y = label.clone()
                data_list.append(data)
        except Exception as e:
            print(f'  Failed to process {blif_name}: {e}')
    return data_list


def evaluate_model(model, data_list, threshold=0.5):
    loader = DataLoader(data_list, batch_size=32, shuffle=False)
    all_scores, all_labels = [], []
    model.eval()
    with torch.no_grad():
        for batch in loader:
            scores = model(batch.x, batch.edge_index)
            all_scores.append(scores.cpu())
            all_labels.append(batch.y.cpu())
    scores = torch.cat(all_scores).float()
    labels = torch.cat(all_labels).float()
    return compute_metrics(scores, labels, threshold)


def find_best_threshold(model, val_data):
    loader = DataLoader(val_data, batch_size=32, shuffle=False)
    all_scores, all_labels = [], []
    model.eval()
    with torch.no_grad():
        for batch in loader:
            scores = model(batch.x, batch.edge_index)
            all_scores.append(scores.cpu())
            all_labels.append(batch.y.cpu())
    scores = torch.cat(all_scores).float()
    labels = torch.cat(all_labels).float()
    best_th, best_f1 = 0.5, 0.0
    for th in [x / 100 for x in range(5, 96, 2)]:
        m = compute_metrics(scores, labels, threshold=th)
        if m['f1'] > best_f1:
            best_f1 = m['f1']
            best_th = th
    return best_th, best_f1


def main():
    print('=' * 70)
    print('  Cross-Design Generalization Evaluation')
    print('=' * 70)

    model_path = os.path.join(MODEL_DIR, 'local_best_model.pt')
    if not os.path.exists(model_path):
        model_path = os.path.join(MODEL_DIR, 'local_seed42.pt')
    print(f'  Model: {model_path}')

    state = torch.load(model_path, map_location='cpu', weights_only=False)
    model = SAGE3(in_channels=10, hidden_channels=128, dropout=0.3)
    model.load_state_dict(state)
    model.eval()
    print(f'  Model params: {sum(p.numel() for p in model.parameters() if p.requires_grad):,}')

    print('\n--- Loading validation data for threshold tuning ---')
    raw = torch.load(DATA_PATH, map_location='cpu', weights_only=False)
    val_data = raw['val']
    best_th, best_val_f1 = find_best_threshold(model, val_data)
    print(f'  Best threshold: {best_th:.3f} (val F1={best_val_f1:.4f})')

    print('\n--- Category-based Zero-Shot Evaluation ---')
    category_results = {}
    for category, blif_files in BLIF_CATEGORIES.items():
        print(f'\n  [{category.upper()}]')
        data_list = load_blif_data(blif_files)
        if not data_list:
            print(f'    No data available')
            continue
        print(f'    {len(data_list)} samples from {len(blif_files)} BLIFs')
        metrics = evaluate_model(model, data_list, threshold=best_th)
        category_results[category] = {k: float(v) for k, v in metrics.items()}
        print(f'    F1={metrics["f1"]:.4f}  Prec={metrics["precision"]:.4f}  '
              f'Rec={metrics["recall"]:.4f}  MSE={metrics["mse"]:.4f}  R2={metrics["r2"]:.4f}')

    print('\n' + '=' * 70)
    print('  Summary: Cross-Design Generalization')
    print('=' * 70)
    print(f'  {"Category":<12} {"F1":>8} {"Precision":>10} {"Recall":>8} {"MSE":>8} {"R2":>8}')
    print('  ' + '-' * 60)
    avg_f1, avg_r2 = 0.0, 0.0
    count = 0
    for category, metrics in sorted(category_results.items()):
        print(f'  {category:<12} {metrics["f1"]:>8.4f} {metrics["precision"]:>10.4f} '
              f'{metrics["recall"]:>8.4f} {metrics["mse"]:>8.4f} {metrics["r2"]:>8.4f}')
        avg_f1 += metrics['f1']
        avg_r2 += metrics['r2']
        count += 1
    if count > 0:
        print('  ' + '-' * 60)
        print(f'  {"Average":<12} {avg_f1/count:>8.4f} {"":>10} {"":>8} {"":>8} {avg_r2/count:>8.4f}')

    print('\n--- Leave-One-Category-Out Evaluation ---')
    all_categories = list(BLIF_CATEGORIES.keys())
    loco_results = {}
    for leave_out in all_categories:
        print(f'\n  Leave-out: {leave_out.upper()}')
        train_cats = [c for c in all_categories if c != leave_out]
        train_data = []
        for cat in train_cats:
            train_data.extend(load_blif_data(BLIF_CATEGORIES[cat]))
        test_data = load_blif_data(BLIF_CATEGORIES[leave_out])
        if not train_data or not test_data:
            print(f'    Insufficient data')
            continue
        print(f'    Train: {len(train_data)} samples')
        print(f'    Test: {len(test_data)} samples')

        torch.manual_seed(42)
        new_model = SAGE3(in_channels=10, hidden_channels=128, dropout=0.3)
        criterion = nn.MSELoss()
        optimizer = torch.optim.AdamW(new_model.parameters(), lr=1e-3, weight_decay=5e-4)
        train_loader = DataLoader(train_data, batch_size=32, shuffle=True)

        best_loss = float('inf')
        patience = 20
        counter = 0
        for epoch in range(100):
            new_model.train()
            total_loss = 0.0
            for batch in train_loader:
                optimizer.zero_grad()
                logits = new_model(batch.x, batch.edge_index)
                loss = criterion(logits, batch.y.float())
                loss.backward()
                optimizer.step()
                total_loss += loss.item()
            avg_loss = total_loss / len(train_loader)
            if avg_loss < best_loss:
                best_loss = avg_loss
                counter = 0
            else:
                counter += 1
                if counter >= patience:
                    break

        val_loader = DataLoader(train_data, batch_size=32, shuffle=False)
        val_scores, val_labels = [], []
        new_model.eval()
        with torch.no_grad():
            for batch in val_loader:
                scores = new_model(batch.x, batch.edge_index)
                val_scores.append(scores.cpu())
                val_labels.append(batch.y.cpu())
        val_scores = torch.cat(val_scores).float()
        val_labels = torch.cat(val_labels).float()
        best_loco_th, best_loco_f1 = 0.5, 0.0
        for th in [x / 100 for x in range(5, 96, 2)]:
            m = compute_metrics(val_scores, val_labels, threshold=th)
            if m['f1'] > best_loco_f1:
                best_loco_f1 = m['f1']
                best_loco_th = th

        metrics = evaluate_model(new_model, test_data, threshold=best_loco_th)
        loco_results[leave_out] = {k: float(v) for k, v in metrics.items()}
        loco_results[leave_out]['threshold'] = best_loco_th
        print(f'    F1={metrics["f1"]:.4f}  Prec={metrics["precision"]:.4f}  '
              f'Rec={metrics["recall"]:.4f}  MSE={metrics["mse"]:.4f}  (th={best_loco_th:.3f})')

    print('\n' + '=' * 70)
    print('  Summary: Leave-One-Category-Out')
    print('=' * 70)
    print(f'  {"Leave-out":<12} {"F1":>8} {"Precision":>10} {"Recall":>8} {"MSE":>8}')
    print('  ' + '-' * 60)
    for cat, metrics in sorted(loco_results.items()):
        print(f'  {cat:<12} {metrics["f1"]:>8.4f} {metrics["precision"]:>10.4f} '
              f'{metrics["recall"]:>8.4f} {metrics["mse"]:>8.4f}')

    results = {
        'cross_design': category_results,
        'leave_one_category_out': loco_results,
        'best_threshold': best_th,
        'model_path': model_path,
    }
    with open(os.path.join(SCRIPT_DIR, 'data', 'cross_design_results.json'), 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\n  Results saved to data/cross_design_results.json')
    print('=' * 70)


if __name__ == '__main__':
    main()
