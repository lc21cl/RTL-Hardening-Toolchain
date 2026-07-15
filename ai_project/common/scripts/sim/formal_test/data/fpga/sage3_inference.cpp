#include "sage3_model.h"
#include <iostream>
#include <vector>
#include <cmath>
#include <numeric>

using namespace sage3;

void sage3_inference(const float* features, const int* edge_index,
                     int num_nodes, int num_edges, float* output) {

    std::vector<std::vector<int>> adj(num_nodes);
    for (int i = 0; i < num_edges; i++) {
        int src = edge_index[i];
        int dst = edge_index[i + num_edges];
        adj[dst].push_back(src);
    }

    std::vector<std::vector<float>> h0(num_nodes, std::vector<float>(IN_CHANNELS));
    for (int i = 0; i < num_nodes; i++) {
        for (int j = 0; j < IN_CHANNELS; j++) {
            h0[i][j] = features[i * IN_CHANNELS + j];
        }
    }

    // Layer 1
    std::vector<std::vector<float>> h1(num_nodes, std::vector<float>(HIDDEN_CHANNELS, 0));
    for (int i = 0; i < num_nodes; i++) {
        std::vector<float> agg(HIDDEN_CHANNELS, 0);
        int deg = adj[i].size();
        if (deg > 0) {
            for (int idx : adj[i]) {
                for (int j = 0; j < HIDDEN_CHANNELS; j++) {
                    for (int k = 0; k < IN_CHANNELS; k++) {
                        agg[j] += h0[idx][k] * conv1_lin_r_weight[k][j];
                    }
                }
            }
            for (int j = 0; j < HIDDEN_CHANNELS; j++) {
                agg[j] /= deg;
            }
        }

        for (int j = 0; j < HIDDEN_CHANNELS; j++) {
            float sum_val = 0;
            for (int k = 0; k < IN_CHANNELS; k++) {
                sum_val += h0[i][k] * conv1_lin_l_weight[k][j];
            }
            h1[i][j] = relu(sum_val + agg[j] + conv1_bias[j]);
        }
    }

    // Layer 2
    std::vector<std::vector<float>> h2(num_nodes, std::vector<float>(HIDDEN_CHANNELS, 0));
    for (int i = 0; i < num_nodes; i++) {
        std::vector<float> agg(HIDDEN_CHANNELS, 0);
        int deg = adj[i].size();
        if (deg > 0) {
            for (int idx : adj[i]) {
                for (int j = 0; j < HIDDEN_CHANNELS; j++) {
                    for (int k = 0; k < HIDDEN_CHANNELS; k++) {
                        agg[j] += h1[idx][k] * conv2_lin_r_weight[k][j];
                    }
                }
            }
            for (int j = 0; j < HIDDEN_CHANNELS; j++) {
                agg[j] /= deg;
            }
        }

        for (int j = 0; j < HIDDEN_CHANNELS; j++) {
            float sum_val = 0;
            for (int k = 0; k < HIDDEN_CHANNELS; k++) {
                sum_val += h1[i][k] * conv2_lin_l_weight[k][j];
            }
            h2[i][j] = relu(sum_val + agg[j] + conv2_bias[j]);
        }
    }

    // Layer 3
    std::vector<std::vector<float>> h3(num_nodes, std::vector<float>(HIDDEN_CHANNELS / 2, 0));
    for (int i = 0; i < num_nodes; i++) {
        std::vector<float> agg(HIDDEN_CHANNELS / 2, 0);
        int deg = adj[i].size();
        if (deg > 0) {
            for (int idx : adj[i]) {
                for (int j = 0; j < HIDDEN_CHANNELS / 2; j++) {
                    for (int k = 0; k < HIDDEN_CHANNELS; k++) {
                        agg[j] += h2[idx][k] * conv3_lin_r_weight[k][j];
                    }
                }
            }
            for (int j = 0; j < HIDDEN_CHANNELS / 2; j++) {
                agg[j] /= deg;
            }
        }

        for (int j = 0; j < HIDDEN_CHANNELS / 2; j++) {
            float sum_val = 0;
            for (int k = 0; k < HIDDEN_CHANNELS; k++) {
                sum_val += h2[i][k] * conv3_lin_l_weight[k][j];
            }
            h3[i][j] = relu(sum_val + agg[j] + conv3_bias[j]);
        }
    }

    // MLP Layer 1
    std::vector<std::vector<float>> mlp1_out(num_nodes, std::vector<float>(32, 0));
    for (int i = 0; i < num_nodes; i++) {
        for (int j = 0; j < 32; j++) {
            float sum_val = 0;
            for (int k = 0; k < HIDDEN_CHANNELS / 2; k++) {
                sum_val += h3[i][k] * mlp1_weight[k][j];
            }
            mlp1_out[i][j] = relu(sum_val + mlp1_bias[j]);
        }
    }

    // MLP Layer 2 + Sigmoid
    for (int i = 0; i < num_nodes; i++) {
        float sum_val = 0;
        for (int k = 0; k < 32; k++) {
            sum_val += mlp1_out[i][k] * mlp2_weight[k][0];
        }
        output[i] = sigmoid(sum_val + mlp2_bias[0]);
    }
}

int main() {
    std::cout << "SAGE3 FPGA Inference - GraphSAGE with Neighbor Aggregation" << std::endl;
    return 0;
}