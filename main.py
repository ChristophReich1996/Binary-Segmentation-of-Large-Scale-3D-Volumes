import torch
from torch.nn import BCELoss
import torchsummary
import numpy as np
import matplotlib.pyplot as plt
from torch.utils.data.dataloader import DataLoader
import os

import Models
import Datasets
import ModelWrapper
import Misc

if __name__ == '__main__':
    # Batch size has to be a factor of the number of devices used in data parallel
    
    os.environ["CUDA_VISIBLE_DEVICES"] = "0" # , 1, 3, 5, 4"
    # model = Models.OccupancyNetwork()
    # model = torch.nn.DataParallel(model)
    # ModelWrapper.OccupancyNetworkWrapper(occupancy_network=model,
    #                                      occupancy_network_optimizer=torch.optim.Adam(model.parameters(), lr=1e-03),
    #                                      training_data=DataLoader(Datasets.WeaponDataset(
    #                                          target_path_volume= '/visinf/home/vilab16/3D_baggage_segmentation/Smiths_LKA_Weapons_Down/len_8/', # "/fastdata/Smiths_LKA_Weapons_Down/len_8/",
    #                                          target_path_label= '/visinf/home/vilab16/3D_baggage_segmentation/Smiths_LKA_Weapons_Down/len_1/', # "/fastdata/Smiths_LKA_Weapons/len_1/",
    #                                          npoints=2 ** 14,
    #                                          side_len=8,
    #                                          length=2600),
    #                                          batch_size=10, shuffle=True, collate_fn=Misc.many_to_one_collate_fn_sample,
    #                                          num_workers=10, pin_memory=True),
    #                                      validation_data=None,
    #                                      test_data=None,
    #                                      loss_function=BCELoss(reduction='mean')
    #                                      ).train(epochs=100, model_save_path='/visinf/home/vilab16/3D_baggage_segmentation/')

    model = torch.load('/visinf/home/vilab16/3D_baggage_segmentation/' + 'occupancy_network_cuda.pt').module
    ModelWrapper.OccupancyNetworkWrapper(occupancy_network=model,
                                         occupancy_network_optimizer=torch.optim.Adam(model.parameters(), lr=1e-05),
                                         training_data=None,
                                         validation_data=None,
                                         test_data=DataLoader(Datasets.WeaponDataset(
                                             target_path_volume= '/visinf/home/vilab16/3D_baggage_segmentation/Smiths_LKA_Weapons_Down/len_8/',
                                             target_path_label= '/visinf/home/vilab16/3D_baggage_segmentation/Smiths_LKA_Weapons_Down/len_1/',
                                             npoints=2 ** 16,
                                             side_len=8,
                                             length=200,
                                             offset=2600,
                                             test=True,
                                             share_box=0),
                                             batch_size=1, shuffle=True, collate_fn=Misc.many_to_one_collate_fn_sample_down,
                                             num_workers=1, pin_memory=True,
                                             ),
                                        loss_function=BCELoss(reduction='mean')
                                        ).test()

            