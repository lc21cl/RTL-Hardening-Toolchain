
#include <iostream>
#include <fstream>
#include <vector>
#include "vulnerability_predictor.h"

int main() {
    VulnerabilityPredictor predictor;
    
    const int num_nodes = 100;
    const int num_edges = 200;
    
    std::vector<float> node_features(num_nodes * INPUT_DIM);
    std::vector<int> edge_index(num_edges * 2);
    std::vector<float> output(num_nodes);
    
    for (int i = 0; i < num_nodes * INPUT_DIM; i++) {
        node_features[i] = static_cast<float>(rand()) / RAND_MAX;
    }
    
    for (int i = 0; i < num_edges * 2; i++) {
        edge_index[i] = rand() % num_nodes;
    }
    
    predictor.forward(
        node_features.data(),
        edge_index.data(),
        output.data(),
        num_nodes,
        num_edges
    );
    
    std::ofstream outfile("output_scores.txt");
    for (int i = 0; i < num_nodes; i++) {
        outfile << i << "," << output[i] << std::endl;
    }
    outfile.close();
    
    std::cout << "Inference complete. Output written to output_scores.txt" << std::endl;
    return 0;
}
