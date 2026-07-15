import os
import sys
import torch
import numpy as np
import matplotlib.pyplot as plt

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(SCRIPT_DIR, 'data', 'training_data.pt')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'data', 'figures')

FEATURE_NAMES = [
    'node_type_pi',
    'node_type_po',
    'node_type_and',
    'node_type_dff',
    'degree_in',
    'degree_out',
    'depth',
    'is_const',
    'path_length_entropy',
    'betweenness_centrality',
]

def load_feature_data():
    if not os.path.exists(DATA_PATH):
        print(f'Error: Data not found at {DATA_PATH}')
        sys.exit(1)
    
    raw = torch.load(DATA_PATH, map_location='cpu', weights_only=False)
    all_data = raw['train'] + raw['val'] + raw['test']
    
    features = []
    labels = []
    
    for data in all_data:
        features.append(data.x.numpy())
        labels.append(data.y.numpy())
    
    features = np.vstack(features)
    labels = np.concatenate(labels)
    
    return features, labels

def compute_distribution_stats(features, labels):
    stats = {}
    
    for i, name in enumerate(FEATURE_NAMES):
        feat = features[:, i]
        pos_mask = labels >= 0.5
        neg_mask = labels < 0.5
        
        stats[name] = {
            'mean': float(np.mean(feat)),
            'std': float(np.std(feat)),
            'min': float(np.min(feat)),
            'max': float(np.max(feat)),
            'median': float(np.median(feat)),
            'pos_mean': float(np.mean(feat[pos_mask])) if np.any(pos_mask) else 0.0,
            'pos_std': float(np.std(feat[pos_mask])) if np.any(pos_mask) else 0.0,
            'neg_mean': float(np.mean(feat[neg_mask])) if np.any(neg_mask) else 0.0,
            'neg_std': float(np.std(feat[neg_mask])) if np.any(neg_mask) else 0.0,
            'corr_with_label': float(np.corrcoef(feat, labels)[0, 1]) if len(feat) > 1 else 0.0,
        }
    
    return stats

def plot_feature_distributions(features, labels):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    fig, axes = plt.subplots(5, 2, figsize=(16, 20))
    axes = axes.flatten()
    
    for i, name in enumerate(FEATURE_NAMES):
        ax = axes[i]
        feat = features[:, i]
        
        pos_mask = labels >= 0.5
        neg_mask = labels < 0.5
        
        bins = np.linspace(np.min(feat), np.max(feat), 50)
        if np.max(feat) == np.min(feat):
            bins = 10
        
        ax.hist(feat[neg_mask], bins=bins, alpha=0.5, label='Non-vulnerable', color='#89b4fa')
        ax.hist(feat[pos_mask], bins=bins, alpha=0.5, label='Vulnerable', color='#f9e2af')
        
        ax.set_title(name.replace('_', ' ').title())
        ax.legend()
        ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'feature_distributions.png'), dpi=150, bbox_inches='tight')
    plt.close()
    
    print('  Saved: feature_distributions.png')

def plot_new_features_scatter(features, labels):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    entropy_idx = FEATURE_NAMES.index('path_length_entropy')
    betweenness_idx = FEATURE_NAMES.index('betweenness_centrality')
    
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    
    ax1 = axes[0]
    ax1.scatter(features[:, entropy_idx], labels, alpha=0.1, s=5)
    ax1.set_xlabel('Path Length Entropy')
    ax1.set_ylabel('Vulnerability Score')
    ax1.set_title('Path Length Entropy vs Vulnerability')
    ax1.grid(True, alpha=0.3)
    
    ax2 = axes[1]
    ax2.scatter(features[:, betweenness_idx], labels, alpha=0.1, s=5)
    ax2.set_xlabel('Betweenness Centrality')
    ax2.set_ylabel('Vulnerability Score')
    ax2.set_title('Betweenness Centrality vs Vulnerability')
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'new_features_scatter.png'), dpi=150, bbox_inches='tight')
    plt.close()
    
    print('  Saved: new_features_scatter.png')

def plot_correlation_heatmap(features, labels):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    all_data = np.column_stack([features, labels])
    names = FEATURE_NAMES + ['vulnerability']
    
    corr_matrix = np.corrcoef(all_data.T)
    
    fig, ax = plt.subplots(figsize=(12, 10))
    im = ax.imshow(corr_matrix, cmap='RdBu_r', vmin=-1, vmax=1)
    
    plt.xticks(range(len(names)), names, rotation=45, ha='right')
    plt.yticks(range(len(names)), names)
    
    for i in range(len(names)):
        for j in range(len(names)):
            text = ax.text(j, i, f'{corr_matrix[i, j]:.2f}',
                           ha='center', va='center',
                           color='white' if abs(corr_matrix[i, j]) > 0.5 else 'black',
                           fontsize=8)
    
    plt.colorbar(im)
    plt.title('Feature Correlation Heatmap')
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'correlation_heatmap.png'), dpi=150, bbox_inches='tight')
    plt.close()
    
    print('  Saved: correlation_heatmap.png')

def main():
    print('=' * 62)
    print('  Feature Distribution Analysis')
    print('=' * 62)
    
    print('\n--- Loading Data ---')
    features, labels = load_feature_data()
    print(f'  Total nodes: {len(features)}')
    print(f'  Feature dimensions: {features.shape[1]}')
    print(f'  Positive ratio: {np.mean(labels >= 0.5) * 100:.2f}%')
    
    print('\n--- Computing Statistics ---')
    stats = compute_distribution_stats(features, labels)
    
    print('\n  Feature Statistics:')
    print('  ' + '-' * 90)
    print(f'  {"Feature":<25} {"Mean":>8} {"Std":>8} {"Min":>8} {"Max":>8} {"Corr":>8}')
    print('  ' + '-' * 90)
    
    for name in FEATURE_NAMES:
        s = stats[name]
        print(f'  {name:<25} {s["mean"]:>8.4f} {s["std"]:>8.4f} {s["min"]:>8.4f} {s["max"]:>8.4f} {s["corr_with_label"]:>8.4f}')
    
    print('\n  New Feature Comparison (Vulnerable vs Non-vulnerable):')
    print('  ' + '-' * 80)
    print(f'  {"Feature":<25} {"Pos Mean":>10} {"Pos Std":>10} {"Neg Mean":>10} {"Neg Std":>10}')
    print('  ' + '-' * 80)
    
    new_features = ['path_length_entropy', 'betweenness_centrality']
    for name in new_features:
        s = stats[name]
        print(f'  {name:<25} {s["pos_mean"]:>10.4f} {s["pos_std"]:>10.4f} {s["neg_mean"]:>10.4f} {s["neg_std"]:>10.4f}')
    
    print('\n--- Generating Visualizations ---')
    plot_feature_distributions(features, labels)
    plot_new_features_scatter(features, labels)
    plot_correlation_heatmap(features, labels)
    
    print('\n' + '=' * 62)
    print('  Analysis Complete')
    print('=' * 62)
    print(f'  Output directory: {OUTPUT_DIR}')

if __name__ == '__main__':
    main()