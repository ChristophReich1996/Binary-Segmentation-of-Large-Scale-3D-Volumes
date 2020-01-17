import torch
from torch.nn import BCELoss
import torchsummary
import numpy as np
import matplotlib.pyplot as plt
import os

import Models
import Datasets
import ModelWrapper


if __name__ == '__main__':
    os.environ["CUDA_VISIBLE_DEVICES"] = "0, 1, 3"
    model = Models.OccupancyNetwork()
    # model = torch.nn.DataParallel(model)
#     model(torch.rand([2, 1, 80, 52, 77]), torch.rand([2 ** 15, 3]))
    ModelWrapper.OccupancyNetworkWrapper(occupancy_network=model,
                                         occupancy_network_optimizer=torch.optim.Adam(model.parameters(),lr=1e-05),
                                         training_data=Datasets.WeaponDataset(
                                                target_path_volume="/fastdata/Smiths_LKA_Weapons/len_8/",
                                                target_path_label="/fastdata/Smiths_LKA_Weapons/len_1/",
                                                npoints=2**14,
                                                side_len=8,
                                                length=2600),
                                         validation_data=None,
                                         test_data=None,
                                         loss_function=BCELoss(reduction='mean')
                                         ).train(epochs=10)
