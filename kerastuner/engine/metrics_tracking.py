# Copyright 2019 The Keras Tuner Authors
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import collections
import copy
import numpy as np
from tensorflow import keras


MetricObservation = collections.namedtuple(
    'MetricObservation',
    'value t')


class MetricsTracker(object):

    def __init__(self, metrics=None):
        self.names = []
        self.directions = {}
        # str -> [MetricObservation]
        self.metrics_history = {}
        self.register_metrics(metrics)

    def exists(self, name):
        return name in self.names

    def register_metrics(self, metrics=None):
        metrics = metrics or []
        for metric in metrics:
            direction = infer_metric_direction(metric)
            self.register(metric.name, direction)

    def register(self, name, direction=None):
        if direction is None:
            direction = infer_metric_direction(name)
        if direction not in {'min', 'max'}:
            raise ValueError(
                '`direction` should be one of '
                '{"min", "max"}, but got: %s' % (direction,))
        if name in self.names:
            raise ValueError('Metric already exists: %s' % (name,))
        self.names.append(name)
        self.directions[name] = direction
        self.metrics_history[name] = []

    def update(self, name, value, t=0):
        value = float(value)
        if not self.exists(name):
            self.register(name)
        history = self.get_history(name)
        history_values = [obs.value for obs in history]
        history.append(MetricObservation(value=value, t=t))

        if not history_values:
            return True

        # Return whether the updated value is best yet seen.
        if self.directions[name] == 'max':
            if value >= np.nanmax(history_values):
                return True
            return False
        if self.directions[name] == 'min':
            if value <= np.nanmin(history_values):
                return True
            return False

    def get_history(self, name):
        if name not in self.names:
            raise ValueError('Unknown metric: %s' % (name,))
        return self.metrics_history[name]

    def set_history(self, name, series):
        assert type(series) == list
        if not self.exists(name):
            self.register(name)
        self.metrics_history[name] = series

    def get_best_value(self, name):
        history = self.get_history(name)
        if not len(history):
            return None

        history_values = [obs.value for obs in history]
        direction = self.directions[name]
        if direction == 'min':
            return min(history_values)
        return max(history_values)

    def get_best_t(self, name):
        history = self.get_history(name)
        if not len(history):
            return None

        history_values = [obs.value for obs in history]
        direction = self.directions[name]
        if direction == 'min':
            t_index = np.argmin(history_values)
        else:
            t_index = np.argmax(history_values)
        return history[t_index].t

    def get_statistics(self, name):
        history = self.get_history(name)
        history_values = [obs.value for obs in history]
        if not len(history_values):
            return {}
        return {
            'min': float(np.nanmin(history_values)),
            'max': float(np.nanmax(history_values)),
            'mean': float(np.nanmean(history_values)),
            'median': float(np.nanmedian(history_values)),
            'var': float(np.nanvar(history_values)),
            'std': float(np.nanstd(history_values))
        }

    def get_last_value(self, name):
        history = self.get_history(name)
        if history:
            return history[-1].value
        else:
            return None

    def get_config(self):
        return {
            'names': copy.copy(self.names),
            'directions': copy.copy(self.directions),
            'metrics_history': copy.copy(self.metrics_history)
        }

    @classmethod
    def from_config(cls, config):
        instance = cls()
        instance.names = config['names']
        instance.directions = config['directions']
        instance.metrics_history = {
            name: [MetricObservation(*obs) for obs in data]
            for name, data in config['metrics_history'].items()}
        return instance


_MAX_METRICS = {
    'Accuracy', 'BinaryAccuracy',
    'CategoricalAccuracy', 'SparseCategoricalAccuracy',
    'TopKCategoricalAccuracy', 'SparseTopKCategoricalAccuracy',
    'TruePositives', 'TrueNegatives',
    'Precision', 'Recall', 'AUC',
    'SensitivityAtSpecificity', 'SpecificityAtSensitivity'
}

_MAX_METRIC_FNS = {
    'accuracy', 'categorical_accuracy', 'binary_accuracy',
    'sparse_categorical_accuracy'
}


def infer_metric_direction(metric):
    # Handle str input and get canonical object.
    if isinstance(metric, str):
        metric_name = metric
        if len(metric_name) > 4 and metric_name[:4] == 'val_':
            metric_name = metric_name[4:]
        if metric_name == 'loss':
            # Special-case the overall loss.
            return 'min'
        try:
            metric = keras.metrics.get(metric_name)
        except ValueError:
            # Default to minimization for unknown metric.
            return 'min'

    # Metric class or function.
    if isinstance(metric, keras.metrics.Metric):
        name = metric.__class__.__name__
        if name == 'MeanMetricWrapper':
            name = metric._fn.__name__
    else:
        name = metric.__name__

    if name in _MAX_METRICS or name in _MAX_METRIC_FNS:
        return 'max'
    return 'min'
