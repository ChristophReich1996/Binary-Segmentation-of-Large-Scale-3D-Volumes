from typing import Callable, Dict, List, Tuple

import numpy as np
import torch
import torch.nn as nn
from tqdm import tqdm
from torch.utils.data.dataloader import DataLoader
import datetime
import Misc
import os
import json


class OccupancyNetworkWrapper(object):
    """
    Implementation of a occupancy network wrapper including training and test method
    """

    def __init__(self, occupancy_network: nn.Module, occupancy_network_optimizer: torch.optim.Optimizer,
                 training_data: torch.utils.data.dataloader,
                 test_data: torch.utils.data.dataloader,
                 validation_data: torch.utils.data.dataloader,
                 loss_function: Callable[[torch.tensor, torch.tensor], torch.tensor], device: str = 'cuda',
                 save_data_path: str = 'Saved_data_', data_folder: str = None) -> None:
        """
        Class constructor
        :param occupancy_network: (nn.Module) Occupancy network for binary segmentation
        :param occupancy_network_optimizer: (torch.optim.Optimizer) Optimizer of the occupancy network
        :param training_data: (torch.utils.data.dataloader) Dataloader including the training dataset
        :param validation_data: (torch.utils.data.dataloader) Dataloader including the validation dataset
        :param test_data: (torch.utils.data.dataloader) Dataloader including the test dataset
        :param loss_function: (Callable[[torch.tensor], torch.tensor]) Loss function to use
        :param device: (str) Device to use while training, validation and testing
        :param data_folder: (str) Folder name inside the main save path
        """
        # Init class variables
        self.occupancy_network = occupancy_network.to(device)
        self.occupancy_network_optimizer = occupancy_network_optimizer
        self.training_data = training_data
        self.test_data = test_data
        self.validation_data = validation_data
        self.loss_function = loss_function
        self.device = device
        self.metrics = dict()
        # Init folder to save models and logs
        if data_folder is None:
            data_folder = str(datetime.datetime.now())
        else:
            data_folder = data_folder + '_' + str(datetime.datetime.now())
        self.path_save_models = os.path.join(save_data_path, 'models_' + data_folder)
        if not os.path.exists(self.path_save_models):
            os.makedirs(self.path_save_models)
        self.path_save_plots = os.path.join(save_data_path, 'plots_' + data_folder)
        if not os.path.exists(self.path_save_plots):
            os.makedirs(self.path_save_plots)
        self.path_save_metrics = os.path.join(save_data_path, 'metrics_' + data_folder)
        if not os.path.exists(self.path_save_metrics):
            os.makedirs(self.path_save_metrics)
        # Save hyperparameters
        hyperparameter = dict()
        hyperparameter['model'] = str(self.occupancy_network)
        hyperparameter['optim'] = str(occupancy_network_optimizer)
        hyperparameter['loss'] = str(loss_function)
        # Save to file
        with open(os.path.join(self.path_save_metrics, 'hyperparameter.txt'), 'w') as json_file:
            json.dump(hyperparameter, json_file)

    def train(self, epochs: int = 100, save_best_model: bool = True, save_model_every_n_epoch: int = 10) -> None:
        """
        Training loop
        :param epochs: (int) Number of epochs to perform
        :param save_best_model: (int) If true the best model is saved
        :param model_save_path: (str) Path to save the best model
        """
        # Model into train mode
        self.occupancy_network.train()
        self.occupancy_network.to(self.device)
        # Init progress bar
        progress_bar = tqdm(total=epochs * len(self.training_data.dataset))
        # Init best loss variable
        best_loss = np.inf
        # Init variables for progress bar
        validation_loss, validation_iou, validation_bb_iou = np.inf, 0, 0
        for epoch in range(epochs):
            # Validate model
            for volumes, coordinates, labels in self.training_data:
                # Update progress bar
                progress_bar.update(volumes.shape[0])
                # Reset gradients
                self.occupancy_network.zero_grad()
                # Data to device
                volumes = volumes.to(self.device)
                coordinates = coordinates.to(self.device)
                labels = labels.to(self.device)
                # Perform model prediction
                prediction = self.occupancy_network(volumes, coordinates)
                # Compute loss
                loss = self.loss_function(prediction, labels)
                # Compute gradients
                loss.backward()
                # Update parameters
                self.occupancy_network_optimizer.step()
                # Update loss info in progress bar
                progress_bar.set_description(
                    'Epoch {}/{}, Best val Loss={:.4f}, Cur val Loss={:.4f}, Cur val IoU={:.4f}, Cur val BB IoU={:.4f}, Loss={:.4f}'.format(
                        epoch + 1, epochs, best_loss, validation_loss, validation_iou, validation_bb_iou, loss.item()))
                # Save loss value and current epoch
                self.logging(metric_name='train_loss', value=loss.item())
                self.logging(metric_name='epoch', value=epoch)
            validation_loss, validation_iou, validation_bb_iou = self.validate()
            # Save validation values
            self.logging(metric_name='validation_loss', value=validation_loss)
            self.logging(metric_name='validation_iou', value=validation_iou)
            self.logging(metric_name='validation_bb_iou', value=validation_bb_iou)
            # Save best model
            if save_best_model and (best_loss > validation_loss):
                torch.save(self.occupancy_network,
                           os.path.join(self.path_save_models, 'occupancy_network_best_' + self.device + '.pt'))
                best_loss = validation_loss
            # Save model
            if epoch % save_model_every_n_epoch == 0:
                torch.save(self.occupancy_network,
                           os.path.join(self.path_save_models,
                                        'occupancy_network_best_' + str(epoch) + '_' + self.device + '.pt'))
            self.save_metrics(self.metrics, path=self.path_save_metrics)
        progress_bar.close()

    @torch.no_grad()
    def validate(self, threshold: float = 0.5, offset: torch.Tensor = torch.tensor([10.0, 10.0, 10.0])) -> Tuple[
        float, float, float]:
        '''
        Validation method
        :param threshold: (bool) Threshold utilized to calc metrics
        :param offset: (torch.Tensor) Offset used for bounding box prediction
        :return: (Tuple[float, float, float]) Validation metrics: loss, iou & bounding box iou
        '''
        # Model into eval mode
        self.occupancy_network.eval()
        # Init list to save loss, iou, bb iou
        loss_values = []
        iou_values = []
        bb_iou_values = []
        # Loop over all indexes
        # Calc no grads
        with torch.no_grad():
            # Get data
            for volume, coordinates, labels, actual in self.validation_data:
                # Add batch size dim to data and to device
                volume = volume.to(self.device)
                coordinates = coordinates.to(self.device)
                labels = labels.to(self.device)
                actual = actual.to(self.device)
                # Get prediction of model
                if isinstance(self.occupancy_network, nn.DataParallel):
                    prediction = self.occupancy_network.module(volume, coordinates)
                else:
                    prediction = self.occupancy_network(volume, coordinates)
                # Calc loss
                loss_values.append(self.loss_function(prediction, labels).item())
                # Calc iou
                iou_values.append(
                    Misc.intersection_over_union(prediction, coordinates, actual[0], threshold=threshold).item())
                # Calc bb iou
                bb_iou_values.append(
                    Misc.intersection_over_union_bounding_box(prediction, coordinates, actual[0],
                                                              threshold=threshold, offset=offset)[0].item())
        return float(np.mean(loss_values)), float(np.mean(iou_values)), float(np.mean(bb_iou_values))

    @torch.no_grad()
    def test(self, draw: bool = True, side_len: int = 1, threshold: float = 0.5,
             offset: torch.tensor = torch.tensor([10.0, 10.0, 10.0])) -> Tuple[float, float, float, float, float]:
        '''
        Testing method
        :param draw: (bool) True if predictions should be drawn and save to .obj file
        :param side_len: (int) Downscale of labels used
        :param threshold: (bool) Threshold utilized to calc metrics
        :param offset: (torch.Tensor) Offset used for bounding box prediction
        :return: (Tuple[float, float, float, float]) Test metrics: iou, iou bounding box, precision, recall & loss
        '''
        # Init progress bar
        progress_bar = tqdm(total=len(self.test_data))
        # Get downsampling factor for input and calculate usampling factor
        upsample_factor = self.test_data.dataset.side_len ** 3
        # Calc no grads
        with torch.no_grad():
            # Iterate over test dataset
            for index, batch in enumerate(self.test_data):
                # Update progress bar
                progress_bar.update(1)
                # Model into eval mode
                self.occupancy_network.eval()
                # Get batch data
                volume, coordinates, labels, actual = batch
                # Data to device
                volume = volume.to(self.device)
                coordinates = coordinates.to(self.device)
                labels = labels.to(self.device)
                actual = actual.to(self.device)
                # Make prediction
                if isinstance(self.occupancy_network, nn.DataParallel):
                    prediction = self.occupancy_network.module(volume, coordinates)
                else:
                    prediction = self.occupancy_network(volume, coordinates)
                # Set offset
                prediction_offset = (prediction > threshold).float()
                # Reshape prediction offset tensor by removing dimension
                prediction_offset = torch.squeeze(prediction_offset)
                # Calc coordinates predicted as a weapon
                weapon_prediction = coordinates[prediction_offset == 1.0]
                # Reshape actual tensor
                actual_ = actual.reshape(-1, 3)
                # Draw weapon prediction
                if draw:
                    Misc.draw_test(weapon_prediction, actual_, volume, side_len, index,
                                   draw_out_path=self.path_save_metrics)
                # Calc intersection over union
                iou = Misc.intersection_over_union(prediction, coordinates, actual[0], threshold=threshold)
                self.logging('iou', iou.item())
                # Calc intersection over union for bounding box
                iou_bounding_box, bounding_box_prediction_shape, bounding_box_error = \
                    Misc.intersection_over_union_bounding_box(prediction, coordinates, actual[0], threshold=threshold,
                                                              offset=offset)
                self.logging('iou_bounding_box', iou_bounding_box.item())
                self.logging('bounding_box_shape_x', bounding_box_prediction_shape[0].item())
                self.logging('bounding_box_shape_y', bounding_box_prediction_shape[1].item())
                self.logging('bounding_box_shape_z', bounding_box_prediction_shape[2].item())
                self.logging('bounding_box_error_x', bounding_box_error[0].item())
                self.logging('bounding_box_error_y', bounding_box_error[1].item())
                self.logging('bounding_box_error_z', bounding_box_error[2].item())
                # Calc precision
                precision = Misc.precision(prediction, coordinates, actual[0], threshold=threshold)
                self.logging('precision', precision.item())
                # Calc recall
                recall = Misc.recall(prediction, coordinates, actual[0], threshold=threshold)
                self.logging('recall', recall.item())
                # Calc loss
                loss = self.loss_function(prediction, labels)
                self.logging('test_loss', loss.item())
                # Get memory consumption of tensors (upsample volume to original)
                size_volume = Misc.get_tensor_size_mb(volume) * upsample_factor
                size_prediction = Misc.get_tensor_size_mb(prediction)
                size_actual = Misc.get_tensor_size_mb(actual)
                self.logging('size_volume', size_volume)
                self.logging('size_prediction', size_prediction)
                self.logging('size_actual', size_actual)

            # Close progress bar
            progress_bar.close()
        # Save metrics
        self.save_metrics(self.metrics, path=self.path_save_metrics)
        # Get average metrics
        test_iou = self.get_average_metric('iou')
        test_iou_bounding_box = self.get_average_metric('iou_bounding_box')
        test_bounding_box_shape_x = self.get_average_metric('bounding_box_shape_x')
        test_bounding_box_shape_y = self.get_average_metric('bounding_box_shape_y')
        test_bounding_box_shape_z = self.get_average_metric('bounding_box_shape_z')
        test_bounding_box_error_x = self.get_average_metric('bounding_box_error_x')
        test_bounding_box_error_y = self.get_average_metric('bounding_box_error_y')
        test_bounding_box_error_z = self.get_average_metric('bounding_box_error_z')
        test_precision = self.get_average_metric('precision')
        test_recall = self.get_average_metric('recall')
        test_loss = self.get_average_metric('test_loss')
        test_size_volume = self.get_average_metric('size_volume')
        test_size_prediction = self.get_average_metric('size_prediction')
        test_size_actual = self.get_average_metric('size_actual')
        # Print metrics
        print('Intersection over union = {}'.format(test_iou))
        print('Intersection over union bounding box = {}'.format(test_iou_bounding_box))
        print('Mean bounding box shape = {}, {}, {}'.format(test_bounding_box_shape_x, test_bounding_box_shape_y,
                                                            test_bounding_box_shape_z))
        print('Mean bounding box error = {}, {}, {}'.format(test_bounding_box_error_x, test_bounding_box_error_y,
                                                            test_bounding_box_error_z))
        print('Precision = {}'.format(test_precision))
        print('Recall = {}'.format(test_recall))
        print('Test loss = {}'.format(test_loss))
        print('Average memory usage per sample: Original volume = {}MB, Label = {}MB, Prediction = {}MB'.format(
            round(test_size_volume, 2), round(test_size_actual, 2), round(test_size_prediction, 2)))
        return test_iou, test_iou_bounding_box, test_precision, test_recall, test_loss

    def logging(self, metric_name: str, value: float) -> None:
        """
        Method writes a given metric value into a dict including list for every metric
        :param metric_name: (str) Name of the metric
        :param value: (float) Value of the metric
        """
        if metric_name in self.metrics:
            if value is None:
                return
            else:
                self.metrics[metric_name].append(value)
        else:
            self.metrics[metric_name] = [value]

    def get_average_metric_for_epoch(self, metric_name: str, epoch: int) -> float:
        """
        Method calculates the average of a metric for a given epoch
        :param metric_name: (str) Name of the metric
        :param epoch: (int) Epoch to average over
        :return: (float) Average metric
        """
        # Convert lists to np.array
        metric = np.array(self.metrics[metric_name])
        epochs = np.array(self.metrics['epoch'])
        # Calc mean
        metric_average = np.mean(metric[np.argwhere(epochs == epoch)])
        return float(metric_average)

    def get_average_metric(self, metric_name: str) -> float:
        """
        Method calculates the average of a metric
        :param metric_name: (str) Name of the metric
        :return: (float) Average metric
        """
        # Convert lists to np.array
        metric = np.array(self.metrics[metric_name])
        # Calc mean
        metric_average = np.mean(metric)
        return float(metric_average)

    @staticmethod
    def save_metrics(metrics: Dict[str, List[float]], path: str, add_time_to_file_name: bool = False) -> None:
        """
        Static method to save dict of metrics
        :param metrics: (Dict[str, List[float]]) Dict including metrics
        :param path: (str) Path to save metrics
        :param add_time_to_file_name: (bool) True if time has to be added to filename of every metric
        """
        # Iterate items in metrics dict
        for metric_name, values in metrics.items():
            # Convert list of values to torch tensor to use build in save method from torch
            values = torch.tensor(values)
            # Save values
            if add_time_to_file_name:
                torch.save(values, path + '/' + metric_name + '_' + datetime.now().strftime("%H:%M:%S") + '.pt')
            else:
                torch.save(values, path + '/' + metric_name + '.pt')
