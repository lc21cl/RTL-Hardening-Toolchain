#include "sage3_lite_model.h"
#include <iostream>
#include <vector>
#include <cmath>
#include <numeric>

using namespace sage3_lite;

void matmul_int8(const uint8_t* weight, float w_scale, int w_zp,
               const float* input, int in_dim, int out_dim, float* output) {
    for (int i = 0; i < out_dim; i++) {
        float sum = 0;
        for (int j = 0; j < in_dim; j++) {
            int8_t w_q = dequantize(weight[i * in_dim + j], w_scale, w_zp);
            sum += (float)w_q * input[j];
        }
        output[i] = sum * w_scale;
    }
}

void sage3_lite_inference(const float* features, const int* edge_index,
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
            std::vector<float> tmp(HIDDEN_CHANNELS, 0);
            for (int idx : adj[i]) {
                matmul_int8(conv1_lin_r_weight, conv1_lin_r_weight_scale, conv1_lin_r_weight_zero_point,
                           h0[idx].data(), IN_CHANNELS, HIDDEN_CHANNELS, tmp.data());
                for (int j = 0; j < HIDDEN_CHANNELS; j++) {
                    agg[j] += tmp[j];
                }
            }
            for (int j = 0; j < HIDDEN_CHANNELS; j++) {
                agg[j] /= deg;
            }
        }
        std::vector<float> lin_out(HIDDEN_CHANNELS, 0);
        matmul_int8(conv1_lin_l_weight, conv1_lin_l_weight_scale, conv1_lin_l_weight_zero_point,
                   h0[i].data(), IN_CHANNELS, HIDDEN_CHANNELS, lin_out.data());
        for (int j = 0; j < HIDDEN_CHANNELS; j++) {
            h1[i][j] = relu(lin_out[j] + agg[j] + conv1_bias_scale * (float)dequantize(conv1_bias[j], conv1_bias_scale, conv1_bias_zero_point));
        }
    }

    // Layer 2
    std::vector<std::vector<float>> h2(num_nodes, std::vector<float>(HIDDEN_CHANNELS, 0));
    for (int i = 0; i < num_nodes; i++) {
        std::vector<float> agg(HIDDEN_CHANNELS, 0);
        int deg = adj[i].size();
        if (deg > 0) {
            std::vector<float> tmp(HIDDEN_CHANNELS, 0);
            for (int idx : adj[i]) {
                matmul_int8(conv2_lin_r_weight, conv2_lin_r_weight_scale, conv2_lin_r_weight_zero_point,
                           h1[idx].data(), HIDDEN_CHANNELS, HIDDEN_CHANNELS, tmp.data());
                for (int j = 0; j < HIDDEN_CHANNELS; j++) {
                    agg[j] += tmp[j];
                }
            }
            for (int j = 0; j < HIDDEN_CHANNELS; j++) {
                agg[j] /= deg;
            }
        }
        std::vector<float> lin_out(HIDDEN_CHANNELS, 0);
        matmul_int8(conv2_lin_l_weight, conv2_lin_l_weight_scale, conv2_lin_l_weight_zero_point,
                   h1[i].data(), HIDDEN_CHANNELS, HIDDEN_CHANNELS, lin_out.data());
        for (int j = 0; j < HIDDEN_CHANNELS; j++) {
            h2[i][j] = relu(lin_out[j] + agg[j] + conv2_bias_scale * (float)dequantize(conv2_bias[j], conv2_bias_scale, conv2_bias_zero_point));
        }
    }

    // Layer 3
    std::vector<std::vector<float>> h3(num_nodes, std::vector<float>(HIDDEN_CHANNELS / 2, 0));
    for (int i = 0; i < num_nodes; i++) {
        std::vector<float> agg(HIDDEN_CHANNELS / 2, 0);
        int deg = adj[i].size();
        if (deg > 0) {
            std::vector<float> tmp(HIDDEN_CHANNELS / 2, 0);
            for (int idx : adj[i]) {
                matmul_int8(conv3_lin_r_weight, conv3_lin_r_weight_scale, conv3_lin_r_weight_zero_point,
                           h2[idx].data(), HIDDEN_CHANNELS, HIDDEN_CHANNELS / 2, tmp.data());
                for (int j = 0; j < HIDDEN_CHANNELS / 2; j++) {
                    agg[j] += tmp[j];
                }
            }
            for (int j = 0; j < HIDDEN_CHANNELS / 2; j++) {
                agg[j] /= deg;
            }
        }
        std::vector<float> lin_out(HIDDEN_CHANNELS / 2, 0);
        matmul_int8(conv3_lin_l_weight, conv3_lin_l_weight_scale, conv3_lin_l_weight_zero_point,
                   h2[i].data(), HIDDEN_CHANNELS, HIDDEN_CHANNELS / 2, lin_out.data());
        for (int j = 0; j < HIDDEN_CHANNELS / 2; j++) {
            h3[i][j] = relu(lin_out[j] + agg[j] + conv3_bias_scale * (float)dequantize(conv3_bias[j], conv3_bias_scale, conv3_bias_zero_point));
        }
    }

    // MLP Layer 1
    std::vector<std::vector<float>> mlp1_out(num_nodes, std::vector<float>(8, 0));
    for (int i = 0; i < num_nodes; i++) {
        matmul_int8(mlp1_weight, mlp1_weight_scale, mlp1_weight_zero_point,
                   h3[i].data(), HIDDEN_CHANNELS / 2, 8, mlp1_out[i].data());
        for (int j = 0; j < 8; j++) {
            mlp1_out[i][j] = relu(mlp1_out[i][j] + mlp1_bias_scale * (float)dequantize(mlp1_bias[j], mlp1_bias_scale, mlp1_bias_zero_point));
        }
    }

    // MLP Layer 2 + Sigmoid
    for (int i = 0; i < num_nodes; i++) {
        float sum_val = 0;
        matmul_int8(mlp2_weight, mlp2_weight_scale, mlp2_weight_zero_point,
                   mlp1_out[i].data(), 8, 1, &sum_val);
        output[i] = sigmoid(sum_val + mlp2_bias_scale * (float)dequantize(mlp2_bias[0], mlp2_bias_scale, mlp2_bias_zero_point));
    }
}

int main() {
    std::cout << "SAGE3-Lite FPGA Inference - INT8 Quantized GraphSAGE" << std::endl;
    return 0;
}