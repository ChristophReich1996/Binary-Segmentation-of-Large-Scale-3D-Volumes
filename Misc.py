from typing import List, Union, Tuple

import torch
import torch.nn as nn
import numpy as np
import os
from pykdtree.kdtree import KDTree

import ModelParts

def intersection_over_union_bounding_box(prediction: torch.tensor, coordinates: torch.tensor, label: torch.tensor,
                                         threshold: float = 0.5,
                                         offset: torch.tensor = torch.tensor([0.0, 0.0, 0.0])) -> torch.tensor:
    # Init kd tree
    kd_tree = KDTree(label.cpu().numpy(), leafsize=16)
    # Estimate which coordinates are weapons
    dist_coordinates_to_label, _ = kd_tree.query(coordinates.cpu().numpy(), k=1)
    del _  # Help the python garbage collector
    dist_coordinates_to_label = torch.from_numpy(dist_coordinates_to_label).to(prediction.device)
    # Estimate which coordinates belongs to a weapon
    coordinates_label = coordinates[dist_coordinates_to_label == 0.0]  # 1 if weapon 0 if not
    if coordinates.shape[0] == 0:
        return torch.tensor([1]), torch.tensor([0, 0, 0]), torch.tensor([0, 0, 0])
    # Get max and min coordinates for bounding box
    max_coordinates_label = torch.max(coordinates_label, dim=0)[0] + offset.to(
        coordinates_label.device)  # Index 0 to get values
    min_coordinates_label = torch.min(coordinates_label, dim=0)[0] - offset.to(
        coordinates_label.device)  # Index 0 to get values
    # print('\n', max_coordinates_label, min_coordinates_label)
    # Apply threshold
    prediction = prediction.view(-1)
    prediction = (prediction > threshold).float()
    if coordinates[prediction == 1.0].shape[0] == 0:
        return torch.tensor([0]), torch.tensor([0, 0, 0]), torch.tensor([0, 0, 0])
    # Get max and min of prediction
    max_coordinates_prediction = torch.max(coordinates[prediction == 1.0], dim=0)[0]  # Index 0 to get values
    min_coordinates_prediction = torch.min(coordinates[prediction == 1.0], dim=0)[0]  # Index 0 to get values
    # print('\n', max_coordinates_prediction, min_coordinates_prediction)
    # Calc volume of label bounding box
    edge_sizes_label = torch.abs(max_coordinates_label - min_coordinates_label)
    bounding_box_label_volume = torch.prod(edge_sizes_label)
    # Calc volume of prediction bounding box
    edge_size_prediction = torch.abs(max_coordinates_prediction - min_coordinates_prediction)
    bounding_box_prediction_volume = torch.prod(edge_size_prediction)
    # Calc coordinates of intersecting bounding box
    overlap = torch.max(torch.zeros(max_coordinates_prediction.shape).to(prediction.device),
                        torch.min(max_coordinates_prediction, max_coordinates_label) - torch.max(
                            min_coordinates_prediction, min_coordinates_label))
    # Calc intersection volume
    intersection = torch.prod(overlap)
    # Calc intersection over union by: intersection / (volume label + volume prediction - intersection)
    iou = intersection / (bounding_box_prediction_volume + bounding_box_label_volume - intersection + + 1e-9)
    # Calc error
    bounding_box_error = torch.max(torch.abs(max_coordinates_prediction - max_coordinates_label),
                                   torch.abs(min_coordinates_prediction - min_coordinates_label))
    return iou.cpu(), edge_size_prediction.cpu(), bounding_box_error.cpu()


def intersection_over_union(prediction: torch.tensor, coordinates: torch.tensor, label: torch.tensor,
                            threshold: float = 0.5) -> torch.tensor:
    """
    Calculates the intersection over union for a given prediction and label.
    Works only with one batch!
    :param prediction: (torch.tensor) Raw prediction of the O-Net (samples)
    :param coordinates: (torch.tensor) Input coordinates of the O-Net (samples, 3)
    :param label: (torch.tensor) High resolution label including only ones (samples, 3)
    :param threshold: (float) Threshold for prediction (default=0.5)
    :return: (torch.tensor) Intersection over union value
    """
    # Init kd tree
    kd_tree = KDTree(label.cpu().numpy(), leafsize=16)
    # Estimate which coordinates are weapons
    dist_coordinates_to_label, _ = kd_tree.query(coordinates.cpu().numpy(), k=1)
    del _  # Help the python garbage collector
    dist_coordinates_to_label = torch.from_numpy(dist_coordinates_to_label).to(prediction.device)
    # Estimate which coordinates belongs to a weapon
    coordinates_label = (dist_coordinates_to_label == 0.0).float()  # 1 if weapon 0 if not
    # Reshape prediction to one dimension
    prediction = prediction.view(-1)
    # Apply threshold
    prediction = (prediction > threshold).float()
    # Calc intersect and union
    sum_of_prediction_and_coordinates_label = prediction + coordinates_label
    intersection = torch.sum((sum_of_prediction_and_coordinates_label == 2).float())
    union = torch.sum((sum_of_prediction_and_coordinates_label >= 1).float())
    # Calc iou
    iou = intersection / (union + 1e-9)
    return iou


def get_tensor_size_mb(tensor: torch.tensor):
    """
    Method that calculates the megabyte needed for a tensor to be stored. Takes into account if tensor is on CPU or GPU.
    :param tensor: (torch.tensor) Input tensor
    :return: (int) Tensor size in megabyte
    """
    return tensor.nelement() * tensor.element_size() * 1e-6


def precision(prediction: torch.tensor, coordinates: torch.tensor, label: torch.tensor,
              threshold: float = 0.5) -> torch.tensor:
    # Init kd tree
    kd_tree = KDTree(label.cpu().numpy(), leafsize=16)
    # Estimate which coordinates are weapons
    dist_coordinates_to_label, _ = kd_tree.query(coordinates.cpu().numpy(), k=1)
    del _  # Help the python garbage collector
    dist_coordinates_to_label = torch.from_numpy(dist_coordinates_to_label).to(prediction.device)
    # Estimate which coordinates belongs to a weapon
    coordinates_label = (dist_coordinates_to_label == 0.0).float()  # 1 if weapon 0 if not
    # Reshape prediction to one dimension
    prediction = prediction.view(-1)
    # Apply threshold
    prediction = (prediction > threshold).float()
    # Calc true positives
    tp = (((prediction == 1.0).float() + (coordinates_label == 1.0).float()) == 2.0).float()
    # Calc False positives
    fp = (((prediction == 1.0).float() + (coordinates_label == 0.0).float()) == 2.0).float()
    # Calc precision
    precision = torch.sum(tp) / (torch.sum(tp + fp) + 1e-9)
    return precision


def recall(prediction: torch.tensor, coordinates: torch.tensor, label: torch.tensor,
           threshold: float = 0.5) -> torch.tensor:
    # Init kd tree
    kd_tree = KDTree(label.cpu().numpy(), leafsize=16)
    # Estimate which coordinates are weapons
    dist_coordinates_to_label, _ = kd_tree.query(coordinates.cpu().numpy(), k=1)
    del _  # Help the python garbage collector
    dist_coordinates_to_label = torch.from_numpy(dist_coordinates_to_label).to(prediction.device)
    # Estimate which coordinates belongs to a weapon
    coordinates_label = (dist_coordinates_to_label == 0.0).float()  # 1 if weapon 0 if not
    # Reshape prediction to one dimension
    prediction = prediction.view(-1)
    # Apply threshold
    prediction = (prediction > threshold).float()
    # Calc true positives
    tp = (((prediction == 1.0).float() + (coordinates_label == 1.0).float()) == 2.0).float()
    # Calc False negatives
    fn = (((prediction == 0.0).float() + (coordinates_label == 1.0).float()) == 2.0).float()
    # Calc precision
    precision = torch.sum(tp) / (torch.sum(tp + fn) + 1e-9)
    return precision


def get_activation(activation: str) -> nn.Sequential:
    """
    Method to return different types of activation functions
    :param activation: (str) Type of activation ('relu', 'leaky relu', 'elu', 'prlu', 'selu', 'sigmoid', 'identity')
    :return: (nn.Sequential) Activation function
    """
    assert activation in ['relu', 'leaky relu', 'elu', 'prelu', 'selu', 'sigmoid', 'identity'], \
        'Activation {} is not available!'.format(activation)
    if activation == 'relu':
        return nn.Sequential(nn.ReLU())
    elif activation == 'leaky relu':
        return nn.Sequential(nn.LeakyReLU())
    elif activation == 'elu':
        return nn.Sequential(nn.ELU())
    elif activation == 'prelu':
        return nn.Sequential(nn.PReLU())
    elif activation == 'selu':
        return nn.Sequential(nn.SELU())
    elif activation == 'sigmoid':
        return nn.Sequential(nn.Sigmoid())
    elif activation == 'identity':
        return nn.Sequential()
    else:
        raise RuntimeError('Activation {} is not available!'.format(activation))


def get_normalization_3d(normalization: str, channels: int, affine: bool = True) -> nn.Sequential:
    """
    Method to return different types of 3D normalization operations
    :param normalization: (str) Type of normalization ('batchnorm', 'instancenorm')
    :param channels: (int) Number of channels to use
    :return: (nn.Sequential) Normalization operation
    """
    assert normalization in ['batchnorm', 'instancenorm'], \
        'Normalization {} is not available!'.format(normalization)
    if normalization == 'batchnorm':
        return nn.Sequential(nn.BatchNorm3d(channels, affine=affine))
    elif normalization == 'instancenorm':
        return nn.Sequential(nn.InstanceNorm3d(channels, affine=affine))
    else:
        raise RuntimeError('Normalization {} is not available!'.format(normalization))


def get_normalization_1d(normalization: str, channels: int, channels_latent: int = None, affine: bool = True) -> Union[
    nn.Sequential, nn.Module]:
    """
    Method to return different types of 1D normalization operations
    :param normalization: (str) Type of normalization ('batchnorm', 'instancenorm')
    :param channels: (int) Number of channels to use
    :return: (nn.Sequential) Normalization operation
    """
    assert normalization in ['batchnorm', 'instancenorm', 'cbatchnorm', 'none'], \
        'Normalization {} is not available!'.format(normalization)
    if normalization == 'batchnorm':
        return nn.Sequential(nn.BatchNorm1d(channels, affine=affine))
    elif normalization == 'instancenorm':
        return nn.Sequential(ModelParts.InstanceNorm1d())
    elif normalization == 'cbatchnorm':
        return ModelParts.ConditionalBatchNorm1d(channels_latent, channels)
    elif normalization == 'none':
        return nn.Sequential()
    else:
        raise RuntimeError('Normalization {} is not available!'.format(normalization))


def get_downsampling_3d(downsampling: str, factor: int = 2, channels: int = 0) -> nn.Sequential:
    """
    Method to return different types of 3D downsampling operations
    :param downsampling: (str) Type of donwsnapling ('maxpool', 'averagepool', 'convolution', 'none')
    :param factor: (int) Factor of downsampling
    :param channels: (int) Number of channels (only for convolution)
    :return: (nn.Sequential) Downsampling operation
    """
    assert downsampling in ['maxpool', 'averagepool', 'convolution', 'none'], \
        'Downsampling {} is not available'.format(downsampling)
    if downsampling == 'maxpool':
        return nn.Sequential(nn.MaxPool3d(kernel_size=factor, stride=factor))
    elif downsampling == 'averagepool':
        return nn.Sequential(nn.AvgPool3d(kernel_size=factor, stride=factor))
    elif downsampling == 'convolution':
        return nn.Sequential(
            nn.Conv3d(in_channels=channels, out_channels=channels, kernel_size=factor, stride=factor, padding=0,
                      bias=True))
    elif downsampling == 'none':
        return nn.Sequential()
    else:
        raise RuntimeError('Downsampling {} is not available'.format(downsampling))


def parse_to_list(
        possible_list: Union[int, float, bool, str, Tuple[int], List[Union[int, float, bool, str, Tuple[int]]]],
        length: int, name: str = '') -> List[Union[int, float, bool, str]]:
    """
    Function checks if parameter possible list is as list or a primitive data type.
    If a primitive data type is present a list with the desired length including the primitive variable in each
    element is returned.
    Examples:   possible_list=True, length=3            ->  [True, True, True]
                possible_list=[3, 4, 5, 6], length=4    ->  [3, 4, 5, 6]
    :param possible_list:
    :param length:
    :param name:
    :return:
    """
    if isinstance(possible_list, list):
        assert len(possible_list) == length, \
            'Length of {} list has to match with the number of blocks'.format(name)
        return possible_list
    else:
        return [possible_list] * length


def many_to_one_collate_fn_sample(batch):
    volumes = torch.stack([elm[0] for elm in batch], dim=0)
    coords = torch.stack([elm[1] for elm in batch], dim=0).view(-1, 3)
    labels = torch.stack([elm[2] for elm in batch], dim=0).view(-1, 1)

    return volumes, coords, labels


def many_to_one_collate_fn_sample_down(batch):
    volumes = torch.stack([elm[0] for elm in batch], dim=0)
    coords = torch.stack([elm[1] for elm in batch], dim=0).view(-1, 3)
    labels = torch.stack([elm[2] for elm in batch], dim=0).view(-1, 1)
    low_volumes = torch.stack([elm[3] for elm in batch], dim=0)

    return volumes, coords, labels, low_volumes


def draw_test(locs, actual, volume, side_len: int, batch_index: int, draw_out_path: str = 'obj'):
    draw_out_path = os.path.join(os.getcwd(), draw_out_path)
    if not os.path.exists(draw_out_path):
        os.mkdir(draw_out_path)

    if batch_index % 25 != 0:
        return

    to_write = locs.cpu().numpy().astype(np.short)
    # Only each 10th as meshlab crashes otherwise
    to_write_act = actual[::10, :].cpu().numpy().astype(np.short)  # actual[::10,:]
    # Mean (shape) centering
    mean = np.array([volume.shape[2] * side_len / 2, volume.shape[3] * side_len / 2, volume.shape[4] * side_len / 2])
    to_write_act = to_write_act - mean
    to_write = to_write - mean  # np.mean(to_write, axis=0)

    # print(locs.shape, to_write.shape, actual.shape, to_write_act.shape)

    with open(os.path.join(draw_out_path, str(batch_index) + '_outfile_pred.obj'), 'w') as f:
        for line in to_write:
            f.write("v " + " " + str(line[0]) + " " + str(line[1]) + " " + str(line[2]) +
                    " " + "0.5" + " " + "0.5" + " " + "1.0" + "\n")
        # for line in to_write_act:
        #     f.write("v " + " " + str(line[0]) + " " + str(line[1]) + " " + str(line[2]) + 
        #     " " + "0.19" + " " + "0.8" + " " + "0.19" + "\n")

        # Corners of volume
        f.write("v " + " " + "0" + " " + "0" + " " + "0" +
                " " + "1.0" + " " + "0.5" + " " + "0.5" + "\n")

        f.write("v " + " " + str(volume.shape[2] * side_len) + " " + "0" + " " + "0" +
                " " + "1.0" + " " + "0.5" + " " + "0.5" + "\n")

        f.write("v " + " " + str(volume.shape[2] * side_len) + " " + str(volume.shape[3] * side_len) + " " + "0" +
                " " + "1.0" + " " + "0.5" + " " + "0.5" + "\n")

        f.write("v " + " " + "0" + " " + str(volume.shape[3] * side_len) + " " + "0" +
                " " + "1.0" + " " + "0.5" + " " + "0.5" + "\n")

        f.write("v " + " " + "0" + " " + "0" + " " + str(volume.shape[4] * side_len) +
                " " + "1.0" + " " + "0.5" + " " + "0.5" + "\n")

        f.write("v " + " " + str(volume.shape[2] * side_len) + " " + "0" + " " + str(volume.shape[4] * side_len) +
                " " + "1.0" + " " + "0.5" + " " + "0.5" + "\n")

        f.write("v " + " " + str(volume.shape[2] * side_len) + " " + str(volume.shape[3] * side_len) + " " + str(
            volume.shape[4] * side_len) +
                " " + "1.0" + " " + "0.5" + " " + "0.5" + "\n")

        f.write("v " + " " + "0" + " " + str(volume.shape[3] * side_len) + " " + str(volume.shape[4] * side_len) +
                " " + "1.0" + " " + "0.5" + " " + "0.5" + "\n")

    with open(os.path.join(draw_out_path, str(batch_index) + '_outfile_label.obj'), 'w') as f:
        # for line in to_write:
        #     f.write("v " + " " + str(line[0]) + " " + str(line[1]) + " " + str(line[2]) + 
        #         " " + "0.5" + " " + "0.5" + " " + "1.0" + "\n")
        for line in to_write_act:
            f.write("v " + " " + str(line[0]) + " " + str(line[1]) + " " + str(line[2]) +
                    " " + "0.19" + " " + "0.8" + " " + "0.19" + "\n")

        # Corners of volume
        f.write("v " + " " + "0" + " " + "0" + " " + "0" +
                " " + "1.0" + " " + "0.5" + " " + "0.5" + "\n")

        f.write("v " + " " + str(volume.shape[2] * side_len) + " " + "0" + " " + "0" +
                " " + "1.0" + " " + "0.5" + " " + "0.5" + "\n")

        f.write("v " + " " + str(volume.shape[2] * side_len) + " " + str(volume.shape[3] * side_len) + " " + "0" +
                " " + "1.0" + " " + "0.5" + " " + "0.5" + "\n")

        f.write("v " + " " + "0" + " " + str(volume.shape[3] * side_len) + " " + "0" +
                " " + "1.0" + " " + "0.5" + " " + "0.5" + "\n")

        f.write("v " + " " + "0" + " " + "0" + " " + str(volume.shape[4] * side_len) +
                " " + "1.0" + " " + "0.5" + " " + "0.5" + "\n")

        f.write("v " + " " + str(volume.shape[2] * side_len) + " " + "0" + " " + str(volume.shape[4] * side_len) +
                " " + "1.0" + " " + "0.5" + " " + "0.5" + "\n")

        f.write("v " + " " + str(volume.shape[2] * side_len) + " " + str(volume.shape[3] * side_len) + " " + str(
            volume.shape[4] * side_len) +
                " " + "1.0" + " " + "0.5" + " " + "0.5" + "\n")

        f.write("v " + " " + "0" + " " + str(volume.shape[3] * side_len) + " " + str(volume.shape[4] * side_len) +
                " " + "1.0" + " " + "0.5" + " " + "0.5" + "\n")


def get_number_of_network_parameters(network: nn.Module) -> int:
    """
    Method estimates the number of learnable parameters in a given network
    :param network: (nn.Module) Network
    :return: (int) Number of learnable parameters
    """
    network.train()
    return sum(p.numel() for p in network.parameters() if p.requires_grad)


class FilePermutation(object):
    """
    Class to shuffle data files
    """

    def __init__(self) -> None:
        self.permute = [756, 1796, 1918, 1115, 139, 1650, 1002, 1906, 519, 1250, 2655,
                        793, 999, 390, 1444, 1519, 2777, 843, 955, 2917, 784, 875,
                        1944, 2009, 2608, 1679, 1507, 202, 2912, 179, 2274, 1052, 2418,
                        1603, 2480, 1051, 1934, 729, 2114, 681, 2134, 408, 2707, 2047,
                        1109, 1278, 1908, 355, 18, 1069, 2077, 2412, 2051, 1233, 2364,
                        858, 1083, 1143, 1805, 1022, 2897, 2709, 370, 2259, 2732, 522,
                        2646, 2911, 2022, 1891, 935, 2023, 336, 2934, 575, 1122, 56,
                        2806, 1362, 1000, 1108, 2172, 1272, 2122, 1748, 2371, 1512, 2669,
                        2840, 257, 432, 1903, 2819, 2240, 2684, 2017, 2697, 413, 2604,
                        531, 2057, 1344, 588, 2637, 2038, 1244, 2734, 2029, 2894, 623,
                        1473, 924, 1410, 2258, 2042, 371, 163, 1991, 1461, 2188, 2941,
                        653, 1852, 491, 2469, 1663, 893, 1769, 2334, 2397, 1691, 1942,
                        138, 1920, 1378, 263, 1403, 2282, 874, 1256, 110, 2587, 244,
                        733, 286, 1423, 1057, 20, 2509, 845, 1685, 81, 1566, 1997,
                        2167, 2856, 2884, 2602, 241, 537, 2440, 416, 1822, 589, 2389,
                        2448, 2865, 1951, 1684, 1614, 2197, 1738, 909, 71, 2335, 1136,
                        379, 714, 896, 347, 1427, 2206, 1308, 735, 2555, 2063, 2312,
                        2705, 1290, 2343, 342, 585, 819, 1882, 2549, 2876, 2442, 294,
                        1787, 2944, 1570, 2596, 2266, 90, 980, 2360, 2255, 2396, 2433,
                        787, 1711, 121, 2165, 1182, 2909, 2921, 51, 1794, 302, 759,
                        2733, 1196, 827, 1931, 962, 1502, 2313, 91, 1897, 2264, 1994,
                        2303, 794, 1628, 2696, 1264, 770, 897, 1261, 2192, 774, 0,
                        2904, 2841, 1422, 1789, 319, 129, 1873, 2416, 1439, 492, 1611,
                        1121, 959, 2279, 2276, 2265, 1894, 189, 2473, 1774, 2317, 1299,
                        46, 1880, 1456, 1972, 1361, 185, 1112, 2848, 2751, 1303, 811,
                        1384, 2914, 2257, 469, 427, 818, 45, 2611, 69, 1326, 1715,
                        2481, 2049, 872, 1674, 1928, 1341, 1003, 1617, 308, 310, 2026,
                        2504, 255, 2372, 2526, 1098, 462, 2278, 2530, 958, 2629, 2402,
                        979, 268, 463, 863, 271, 2936, 1458, 136, 2578, 533, 2672,
                        528, 2225, 2330, 503, 321, 328, 246, 1850, 2514, 841, 2435,
                        2449, 569, 1763, 482, 1518, 1015, 2292, 2690, 1296, 2254, 481,
                        796, 905, 2173, 771, 1368, 464, 993, 1353, 2451, 553, 1171,
                        1255, 1760, 2200, 532, 2176, 1509, 86, 2156, 1048, 1033, 2826,
                        1946, 1546, 2786, 1537, 1924, 2755, 552, 801, 1318, 1802, 2072,
                        1245, 2455, 104, 1557, 931, 199, 1889, 1390, 840, 2186, 467,
                        871, 809, 2089, 2484, 107, 2101, 1178, 2133, 2152, 126, 2943,
                        1128, 1954, 779, 1696, 2523, 2044, 1713, 2838, 967, 697, 2321,
                        2126, 1913, 2853, 780, 156, 2742, 1666, 1087, 341, 1187, 1168,
                        144, 109, 2945, 1565, 2867, 643, 1746, 22, 1550, 160, 2304,
                        1243, 1495, 1317, 1545, 828, 2355, 2532, 2487, 1095, 1014, 2275,
                        1945, 2927, 1455, 270, 2338, 1780, 2722, 314, 2937, 2634, 1484,
                        1188, 1831, 620, 1990, 106, 876, 1214, 287, 1309, 2580, 2319,
                        1657, 949, 1082, 2444, 362, 2502, 992, 1421, 1936, 633, 1263,
                        2202, 2378, 204, 837, 2456, 2333, 212, 2581, 1664, 2168, 1564,
                        940, 2588, 1295, 2737, 698, 2623, 1770, 738, 358, 576, 2064,
                        815, 996, 1720, 1030, 788, 1613, 2380, 256, 266, 1092, 997,
                        757, 1974, 14, 1703, 239, 1590, 1103, 2951, 2928, 2718, 1947,
                        2104, 2575, 1466, 1063, 1107, 245, 1274, 989, 954, 711, 2557,
                        1692, 1219, 2674, 2224, 1849, 1629, 303, 2938, 2656, 1571, 297,
                        1106, 1476, 2153, 514, 228, 72, 2873, 1129, 152, 2870, 594,
                        1732, 1521, 604, 1884, 2213, 52, 560, 957, 509, 910, 2636,
                        662, 792, 2337, 497, 1654, 385, 1707, 908, 1637, 1751, 1875,
                        1818, 824, 1520, 2891, 1525, 2620, 1914, 1029, 1735, 127, 2868,
                        1306, 13, 2673, 102, 2028, 135, 1761, 1387, 2769, 2409, 382,
                        1860, 644, 1185, 592, 849, 548, 2492, 1586, 765, 2438, 1210,
                        1085, 2837, 2030, 1631, 1826, 471, 1020, 326, 551, 1853, 1328,
                        650, 2053, 2500, 2631, 1111, 657, 2462, 2170, 1602, 783, 2146,
                        29, 130, 540, 2226, 2821, 2112, 651, 645, 2263, 671, 1736,
                        2245, 1145, 417, 6, 1380, 1336, 1217, 2843, 1724, 2143, 75,
                        2681, 723, 1289, 2601, 2538, 175, 1165, 2723, 755, 591, 1253,
                        1798, 252, 1377, 1164, 2353, 1618, 280, 1307, 1001, 582, 1393,
                        2490, 861, 1952, 337, 100, 1370, 2874, 1104, 763, 2762, 323,
                        2040, 2899, 24, 2403, 2142, 2088, 2626, 2682, 867, 279, 895,
                        1839, 1172, 1400, 2252, 1470, 289, 2, 216, 982, 1940, 2529,
                        1449, 2341, 920, 817, 1348, 1004, 917, 915, 885, 599, 695,
                        2479, 2109, 411, 2024, 1527, 1862, 1297, 1425, 295, 778, 2058,
                        60, 1398, 1269, 2773, 736, 2816, 1723, 789, 2272, 1180, 2562,
                        2882, 2633, 2467, 968, 2877, 1588, 621, 2175, 2839, 188, 1404,
                        1670, 2132, 2436, 1019, 1394, 484, 2065, 439, 1877, 1828, 1300,
                        2221, 878, 941, 1043, 1553, 346, 2488, 972, 200, 1993, 799,
                        2060, 2516, 2183, 1469, 2586, 2866, 1856, 565, 1102, 2715, 350,
                        672, 1026, 410, 2518, 1776, 1580, 988, 1077, 1457, 1995, 2568,
                        747, 450, 605, 1626, 1861, 873, 822, 1131, 1659, 1646, 856,
                        2381, 1459, 1899, 1223, 220, 1749, 167, 1633, 2875, 2228, 2946,
                        2725, 1987, 455, 544, 437, 1313, 1743, 1388, 1155, 1960, 1958,
                        1418, 590, 606, 1874, 839, 950, 1623, 2776, 2267, 1331, 2037,
                        2832, 193, 2495, 197, 2570, 313, 150, 329, 2491, 269, 1009,
                        1369, 2683, 2326, 1734, 2375, 1984, 2693, 1428, 2842, 59, 1604,
                        2318, 977, 2107, 2645, 1986, 1538, 381, 888, 2708, 1452, 2482,
                        884, 1236, 291, 1432, 48, 2667, 641, 1133, 2766, 2427, 1202,
                        659, 430, 626, 1407, 2895, 2748, 153, 2068, 925, 2879, 2222,
                        2092, 2446, 2123, 1792, 44, 1640, 1676, 2231, 1615, 2454, 1644,
                        1773, 133, 1205, 194, 2050, 2813, 1293, 276, 402, 2130, 864,
                        2561, 632, 2105, 1514, 394, 431, 240, 2342, 161, 2163, 35,
                        2955, 1430, 253, 2496, 2460, 433, 2332, 1076, 25, 1056, 1298,
                        2076, 2182, 1467, 1814, 1969, 2356, 1222, 752, 1246, 746, 761,
                        1066, 196, 1482, 177, 2855, 1868, 852, 1959, 1964, 760, 506,
                        678, 198, 894, 1668, 866, 2124, 2365, 1669, 2915, 2537, 2067,
                        1900, 1273, 2767, 1533, 1281, 1372, 2351, 227, 1268, 2069, 614,
                        670, 1572, 677, 2227, 1408, 235, 1135, 1147, 377, 2569, 2511,
                        2534, 2012, 1405, 2700, 600, 1971, 2499, 2447, 1701, 1810, 1249,
                        2141, 1436, 122, 440, 790, 1018, 2113, 331, 1441, 1970, 2505,
                        1199, 307, 2280, 1312, 120, 1620, 1215, 447, 21, 1346, 487,
                        2768, 1562, 1324, 421, 2457, 2930, 1709, 870, 2753, 2799, 170,
                        2533, 2622, 1061, 1807, 1283, 542, 489, 344, 2117, 772, 1544,
                        1305, 2920, 2062, 597, 2443, 2852, 1729, 2281, 1569, 731, 251,
                        2212, 1702, 448, 2952, 2475, 41, 2728, 2413, 1808, 1342, 2410,
                        2361, 357, 1354, 242, 1419, 1975, 1447, 311, 207, 457, 1845,
                        2018, 2540, 2846, 2614, 613, 2164, 426, 2933, 636, 2219, 2609,
                        1213, 1809, 2847, 1847, 2797, 147, 1062, 948, 2352, 740, 2759,
                        369, 2461, 2008, 2174, 2367, 62, 2803, 407, 1116, 1478, 1955,
                        37, 2198, 921, 900, 210, 648, 1712, 676, 1240, 221, 213,
                        580, 446, 1047, 1034, 1542, 2735, 333, 508, 2103, 2093, 1167,
                        721, 700, 105, 2641, 1757, 2031, 2691, 512, 2893, 1156, 2576,
                        366, 1276, 1024, 1680, 1438, 2552, 2223, 359, 1371, 687, 79,
                        2464, 1598, 649, 2745, 1829, 2589, 1501, 368, 1123, 960, 1627,
                        2284, 2740, 1067, 1608, 1516, 692, 1124, 1793, 995, 1391, 2574,
                        94, 182, 465, 612, 513, 131, 114, 2110, 1587, 1208, 2417,
                        1911, 215, 2300, 2565, 2822, 2918, 640, 82, 1915, 524, 2493,
                        2301, 1499, 23, 203, 116, 1148, 2244, 1334, 2605, 1745, 2128,
                        389, 1832, 821, 1402, 1248, 625, 1170, 2366, 1487, 520, 2305,
                        690, 183, 2638, 1910, 795, 663, 1840, 724, 1416, 903, 1870,
                        830, 913, 95, 2836, 1302, 2423, 1865, 2005, 1242, 610, 2750,
                        1080, 2545, 422, 1058, 247, 2430, 2892, 1184, 667, 2289, 2913,
                        1442, 767, 2800, 820, 2607, 2649, 2613, 2070, 10, 237, 327,
                        2507, 1357, 673, 510, 2610, 2902, 191, 1785, 1183, 1150, 2196,
                        1804, 474, 1038, 966, 946, 384, 1481, 2277, 2851, 515, 1286,
                        1591, 2082, 2680, 538, 1158, 2543, 2405, 547, 1699, 2594, 936,
                        800, 452, 1096, 299, 305, 1375, 1496, 1916, 2368, 2166, 2658,
                        2256, 1023, 1820, 797, 2374, 260, 2661, 607, 1864, 1547, 1917,
                        15, 1683, 180, 2650, 1905, 716, 1258, 124, 2135, 814, 92,
                        1935, 851, 2567, 2080, 1548, 2160, 49, 1016, 195, 1609, 2199,
                        173, 2860, 1169, 2883, 1292, 2344, 380, 458, 1675, 316, 2675,
                        58, 891, 2632, 61, 2712, 665, 1881, 751, 495, 835, 1867,
                        702, 1812, 1315, 485, 2880, 1694, 1594, 1652, 1907, 2390, 2075,
                        2872, 2916, 2090, 2513, 1624, 1013, 367, 2665, 1446, 1790, 1364,
                        78, 2782, 1791, 2539, 1132, 2098, 1497, 2585, 2652, 616, 1511,
                        1351, 1786, 1151, 943, 860, 55, 1937, 1741, 1752, 1682, 2154,
                        1064, 680, 2327, 804, 602, 2564, 2102, 927, 1678, 149, 2754,
                        712, 217, 2522, 2592, 391, 2619, 1872, 516, 1660, 2150, 1337,
                        2386, 1081, 1622, 2191, 2603, 1363, 67, 1146, 1477, 2749, 1017,
                        945, 232, 348, 1641, 2825, 2401, 660, 798, 2056, 1144, 134,
                        1927, 1105, 2357, 141, 12, 2393, 349, 2635, 1647, 2052, 1200,
                        1574, 1515, 1113, 1939, 2907, 1412, 2428, 405, 2339, 1349, 2421,
                        125, 745, 1795, 42, 1898, 2701, 1161, 1099, 2045, 352, 2111,
                        17, 1771, 1159, 1689, 1181, 2285, 438, 1140, 2074, 965, 2850,
                        236, 87, 1175, 403, 2121, 499, 209, 639, 496, 627, 2703,
                        1610, 1277, 112, 969, 443, 2864, 768, 2294, 1506, 265, 1784,
                        2348, 734, 53, 2671, 2370, 1933, 1239, 2677, 1356, 205, 2288,
                        1823, 1174, 2905, 155, 1992, 2185, 1639, 372, 1177, 918, 85,
                        2595, 157, 2425, 2237, 2054, 1379, 1710, 679, 2214, 132, 2236,
                        1396, 2559, 2208, 1863, 4, 1532, 1579, 2627, 2640, 1211, 2071,
                        1842, 1037, 631, 1730, 2201, 2654, 2239, 493, 290, 374, 2033,
                        2810, 974, 1584, 2298, 1912, 722, 675, 557, 2618, 857, 1434,
                        1578, 501, 137, 708, 2520, 2802, 97, 2685, 2747, 296, 1173,
                        1192, 436, 223, 2729, 994, 541, 2032, 1965, 476, 525, 2161,
                        1314, 2666, 151, 1596, 2719, 2834, 1941, 2320, 561, 2020, 2593,
                        222, 978, 868, 1988, 2544, 1755, 682, 1489, 2345, 1325, 309,
                        103, 1465, 142, 2127, 2519, 2903, 865, 2195, 504, 363, 2726,
                        1389, 2807, 1468, 201, 1414, 2790, 933, 2727, 2210, 1841, 2002,
                        901, 1426, 171, 2094, 701, 882, 1021, 539, 963, 2615, 578,
                        2035, 2136, 1498, 1754, 1806, 2668, 1301, 2716, 1888, 1816, 742,
                        2651, 442, 1561, 2714, 684, 2233, 2159, 2013, 1254, 318, 2489,
                        564, 635, 563, 2551, 96, 938, 545, 1383, 521, 1114, 304,
                        2577, 2419, 2325, 2558, 1904, 2541, 477, 1797, 2315, 2531, 2854,
                        686, 2548, 782, 2388, 683, 2849, 445, 2217, 2830, 1304, 947,
                        693, 566, 2463, 2434, 2763, 1234, 2888, 143, 2119, 944, 1166,
                        2079, 2687, 414, 2171, 404, 2286, 2194, 1227, 833, 2027, 2043,
                        2346, 805, 1431, 1833, 1645, 1074, 877, 1073, 273, 2445, 2556,
                        2085, 1231, 186, 1053, 570, 406, 1226, 2663, 2598, 2756, 1742,
                        1417, 2501, 2216, 775, 642, 2203, 2019, 803, 694, 838, 826,
                        929, 1464, 1385, 2859, 1186, 1747, 1878, 691, 2235, 2527, 2929,
                        2521, 1225, 1705, 2271, 1486, 2269, 802, 2144, 762, 1448, 278,
                        1567, 2494, 1632, 34, 1139, 1838, 973, 725, 1973, 88, 1479,
                        2296, 2676, 1190, 2784, 8, 1549, 2817, 853, 1310, 577, 1876,
                        1661, 400, 1044, 2314, 1727, 2818, 320, 1360, 2439, 1815, 1320,
                        2948, 987, 1599, 2001, 2291, 1335, 661, 211, 806, 2935, 83,
                        2717, 2205, 1209, 2528, 298, 1649, 2322, 2896, 1027, 1045, 1141,
                        30, 2468, 937, 2382, 1871, 1919, 2791, 2034, 145, 2158, 373,
                        1070, 720, 2566, 1126, 2887, 2096, 1582, 2706, 709, 2900, 1775,
                        1415, 555, 816, 2246, 2184, 1575, 748, 1843, 1539, 2644, 2881,
                        456, 1374, 1088, 2486, 2099, 1524, 2844, 1279, 27, 2730, 1573,
                        2827, 2404, 1265, 2384, 2890, 2789, 2349, 165, 2261, 615, 2046,
                        494, 1568, 842, 2100, 1485, 534, 1635, 238, 1665, 420, 453,
                        773, 1041, 2780, 398, 1977, 1100, 292, 248, 2659, 511, 267,
                        2293, 1358, 2007, 2086, 272, 1055, 1399, 2162, 66, 546, 1224,
                        2180, 1163, 568, 1541, 1075, 1949, 31, 1846, 1036, 669, 2702,
                        324, 2253, 2328, 2118, 2148, 1523, 451, 2398, 1060, 2290, 1228,
                        1893, 634, 1740, 1120, 409, 1706, 2695, 1229, 2779, 1929, 2795,
                        1885, 1803, 1359, 274, 2400, 1474, 919, 854, 2459, 2283, 2512,
                        224, 1322, 1028, 89, 629, 2452, 2014, 2924, 1836, 2744, 850,
                        832, 282, 1282, 2472, 1149, 281, 36, 652, 911, 1117, 1392,
                        2211, 1605, 386, 2820, 603, 1765, 1980, 1967, 1979, 1333, 2600,
                        2041, 2793, 1433, 2809, 1536, 655, 1119, 689, 1032, 624, 2738,
                        461, 340, 985, 898, 1756, 234, 523, 1247, 2437, 744, 2138,
                        930, 1435, 1230, 598, 2078, 1737, 335, 1321, 1054, 1799, 169,
                        554, 769, 429, 2408, 1772, 668, 1719, 813, 529, 1011, 1619,
                        2584, 2426, 1237, 2713, 1207, 70, 2939, 1406, 1531, 1708, 2775,
                        976, 2376, 2268, 262, 444, 1332, 785, 2116, 2508, 1983, 1687,
                        214, 2169, 2429, 737, 396, 2625, 990, 1559, 1078, 176, 593,
                        285, 218, 1985, 2694, 1483, 1042, 356, 2299, 1347, 2624, 1800,
                        1395, 39, 500, 2770, 1589, 2340, 2606, 928, 2599, 111, 2147,
                        1089, 674, 727, 2242, 2925, 1194, 2359, 881, 1978, 1450, 766,
                        2563, 1858, 1612, 1902, 1397, 2474, 2922, 2582, 2662, 2129, 1577,
                        2535, 2906, 2004, 2639, 2391, 2785, 2073, 1097, 2757, 536, 108,
                        2006, 2453, 2746, 646, 1350, 1006, 2157, 914, 939, 43, 2621,
                        365, 2572, 47, 2478, 1597, 1526, 1327, 174, 1093, 80, 449,
                        777, 1648, 825, 2310, 1999, 2262, 2932, 1462, 550, 791, 596,
                        2422, 786, 1125, 1926, 1753, 2377, 1179, 2125, 353, 1025, 2553,
                        317, 1866, 2204, 2450, 1492, 2181, 2886, 1508, 2021, 1859, 2229,
                        1287, 1386, 584, 848, 2323, 618, 2885, 2711, 57, 63, 1503,
                        1059, 473, 1630, 33, 1049, 2178, 284, 475, 883, 1480, 559,
                        73, 1259, 1031, 1493, 2097, 1505, 332, 1517, 5, 2187, 1932,
                        1869, 1554, 1758, 1376, 530, 1827, 1837, 2385, 1638, 2758, 2781,
                        259, 2424, 7, 1251, 168, 2871, 1592, 753, 162, 2179, 1504,
                        2003, 932, 2796, 28, 322, 118, 1595, 376, 1957, 2524, 2250,
                        275, 435, 98, 656, 1090, 658, 581, 2829, 2000, 1851, 1220,
                        1529, 113, 412, 454, 2814, 654, 983, 2617, 1065, 2066, 732,
                        2811, 2546, 2630, 2573, 1717, 1552, 1966, 99, 902, 1563, 401,
                        1962, 1007, 889, 2857, 1381, 1722, 1152, 2316, 1510, 1673, 2721,
                        2407, 1819, 2220, 2698, 2306, 2015, 2642, 1777, 172, 741, 1643,
                        1778, 855, 339, 1238, 293, 483, 2311, 1813, 961, 1998, 1118,
                        1728, 1982, 1084, 713, 2815, 1731, 574, 1621, 2189, 2247, 472,
                        1288, 233, 26, 1454, 460, 1704, 2643, 1463, 2788, 2648, 846,
                        2953, 1475, 2387, 2689, 16, 2761, 1953, 301, 2831, 415, 587,
                        699, 726, 1367, 2824, 1593, 2547, 468, 184, 1989, 277, 2406,
                        1766, 1201, 758, 288, 934, 300, 2025, 2889, 2324, 1601, 2863,
                        1130, 1739, 2414, 2804, 1551, 1319, 364, 2657, 1500, 187, 164,
                        1068, 844, 425, 1445, 306, 470, 951, 710, 1409, 1768, 517,
                        2432, 942, 1762, 77, 1212, 2249, 518, 2792, 1221, 1779, 1235,
                        330, 486, 1535, 1733, 146, 1323, 387, 479, 880, 2081, 1555,
                        2307, 1443, 2295, 1329, 1203, 2287, 2670, 975, 847, 68, 2087,
                        2347, 101, 423, 1191, 9, 1581, 478, 1275, 1625, 2597, 226,
                        315, 2395, 1343, 1887, 2787, 2155, 1848, 1961, 2954, 2466, 115,
                        1811, 38, 2394, 549, 1204, 696, 776, 2926, 829, 2583, 360,
                        2193, 1681, 1925, 2149, 617, 2736, 1616, 859, 1892, 2805, 1206,
                        1162, 718, 1291, 2329, 1651, 706, 823, 2091, 2628, 345, 1714,
                        1316, 1522, 2833, 2692, 562, 1817, 2942, 2808, 208, 1855, 2431,
                        998, 1530, 498, 2771, 502, 1585, 1153, 2498, 2331, 1556, 140,
                        2878, 981, 807, 1345, 899, 2741, 2739, 831, 1923, 2273, 383,
                        2055, 2510, 1513, 1656, 2336, 2731, 666, 1576, 2420, 1270, 1494,
                        2664, 1189, 1886, 1401, 535, 1930, 351, 225, 2699, 719, 1420,
                        2036, 2218, 586, 1091, 1338, 2678, 1662, 2653, 1948, 912, 2869,
                        2151, 1677, 2358, 608, 1583, 638, 2783, 1488, 2828, 1879, 1830,
                        2861, 984, 2483, 567, 1437, 1366, 1725, 2061, 258, 1726, 1956,
                        1365, 2647, 2350, 2243, 2571, 611, 230, 1658, 1086, 2369, 1922,
                        2238, 573, 571, 1010, 1267, 1072, 1241, 1721, 250, 1781, 1642,
                        3, 1901, 1783, 375, 2232, 2177, 1938, 243, 1160, 1491, 2497,
                        1560, 2752, 1636, 764, 1996, 630, 490, 2525, 1540, 907, 54,
                        2302, 1718, 986, 1767, 1963, 2506, 834, 952, 488, 2411, 2039,
                        424, 1655, 2137, 1909, 2616, 2931, 728, 507, 879, 2724, 2234,
                        1142, 397, 441, 1844, 1340, 1339, 2190, 1280, 1981, 1424, 2131,
                        1138, 1671, 1157, 74, 781, 1039, 836, 808, 923, 558, 609,
                        647, 886, 399, 869, 812, 2794, 2710, 1008, 1197, 1460, 2248,
                        2554, 2660, 1750, 2949, 2947, 543, 2812, 334, 622, 2270, 2251,
                        1744, 1821, 1834, 119, 1943, 434, 1137, 1528, 2679, 1429, 1890,
                        2139, 418, 628, 325, 1373, 1193, 1693, 166, 2415, 2095, 312,
                        1094, 1690, 2908, 707, 505, 1921, 730, 1176, 2798, 1883, 1352,
                        343, 1050, 1012, 2399, 2704, 2140, 378, 2686, 743, 2517, 154,
                        749, 1110, 2835, 2858, 264, 1895, 1471, 887, 2919, 601, 1134,
                        1257, 2862, 2471, 2084, 572, 76, 40, 178, 1440, 2363, 1759,
                        1716, 1543, 1788, 466, 1835, 953, 2591, 2476, 2392, 1232, 2309,
                        261, 2354, 2764, 2120, 2950, 556, 971, 717, 338, 1101, 1260,
                        1558, 2011, 1700, 926, 2579, 1606, 2477, 181, 2016, 1825, 428,
                        1252, 2743, 206, 2536, 1896, 192, 685, 964, 393, 64, 1686,
                        922, 1040, 419, 1672, 970, 2550, 361, 2297, 459, 1600, 159,
                        11, 2207, 1472, 705, 2215, 1266, 19, 50, 231, 890, 1451,
                        1490, 32, 2083, 1071, 65, 1824, 2772, 2106, 579, 527, 1667,
                        283, 2612, 1453, 2720, 219, 249, 2778, 1697, 1801, 480, 148,
                        2241, 956, 2010, 595, 1976, 862, 1046, 1294, 906, 704, 2590,
                        2145, 2260, 1411, 664, 392, 84, 2823, 2308, 1330, 1355, 229,
                        2470, 2688, 2898, 2923, 190, 1413, 688, 1764, 1005, 2458, 1262,
                        2940, 2209, 1968, 1216, 2465, 904, 1127, 1634, 810, 1782, 1079,
                        158, 1607, 2760, 1195, 2801, 1688, 2910, 2503, 2441, 2373, 2845,
                        739, 2115, 117, 388, 703, 1698, 128, 2108, 2059, 583, 2048,
                        2485, 1, 1857, 1695, 2230, 1271, 2901, 395, 2560, 1534, 1154,
                        2515, 916, 526, 715, 1854, 619, 637, 1198, 754, 123, 93,
                        1285, 2774, 1218, 1035, 2362, 1950, 750, 1311, 2542, 991, 2383,
                        1284, 2765, 892, 1653, 1382, 2379, 354, 254]

        # TODO: fix permutation

        # custom permutation that only considers files that are in the directory
        import os
        file_names = os.listdir(
            "/fastdata/Smiths_LKA_Weapons_Down/len_8/")  # '/fastdata/Smiths_LKA_WeaponsDown/len_8/'
        ending = '_label.npy'
        permutation = []
        for file_name in file_names:
            if ending in file_name:
                permutation.append(file_name[:-len(ending)])

        self.permute = permutation

    def __getitem__(self, index: int):
        """
        Returns the permuteded index
        :param index: (int) Input index
        :return: (int) New index
        """
        return self.permute[index]
