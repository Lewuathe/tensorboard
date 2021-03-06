# Copyright 2017 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""The TensorBoard Distributions (a.k.a. compressed histograms) plugin.

This plugin provides a different view for the same data that is used for
the histograms plugin. Its `/distributions` route returns a result of
the form

    [[wall_time, step, [[bp_1, icdf_1], ..., [bp_k, icdf_k]]], ...],

where each `icdf_i` is the value of the inverse CDF of the probability
distribution provided by the data evaluated at `bp_i / 10000`. That is,
each `icdf_i` is the lowest value such that `bp_i / 10000` of the values
in the original data fall below `icdf_i`.

The `bp_i` are the fixed values of `NORMAL_HISTOGRAM_BPS` in the
`compressor` module of this package; `k` is `len(NORMAL_HISTOGRAM_BPS)`.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from werkzeug import wrappers

from tensorboard.backend import http_util
from tensorboard.plugins import base_plugin
from tensorboard.plugins.distribution import compressor
from tensorboard.plugins.histogram import histograms_plugin


class DistributionsPlugin(base_plugin.TBPlugin):
  """Distributions Plugin for TensorBoard.

  This supports both old-style summaries (created with TensorFlow ops
  that output directly to the `histo` field of the proto) and new-style
  summaries (as created by the `tensorboard.plugins.histogram.summary`
  module).
  """

  plugin_name = 'distributions'

  def __init__(self, context):
    """Instantiates DistributionsPlugin via TensorBoard core.

    Args:
      context: A base_plugin.TBContext instance.
    """
    self._histograms_plugin = histograms_plugin.HistogramsPlugin(context)
    self._multiplexer = context.multiplexer

  def get_plugin_apps(self):
    return {
        '/distributions': self.distributions_route,
        '/tags': self.tags_route,
    }

  def is_active(self):
    """This plugin is active iff any run has at least one histogram tag.

    (The distributions plugin uses the same data source as the histogram
    plugin.)
    """
    return self._histograms_plugin.is_active()

  def distributions_impl(self, tag, run):
    """Result of the form `(body, mime_type)`, or `ValueError`."""
    (histograms, mime_type) = self._histograms_plugin.histograms_impl(
        tag, run, downsample_to=None)
    return ([self._compress(histogram) for histogram in histograms],
            mime_type)

  def _compress(self, histogram):
    (wall_time, step, buckets) = histogram
    converted_buckets = compressor.compress_histogram(buckets)
    return [wall_time, step, converted_buckets]

  def index_impl(self):
    return self._histograms_plugin.index_impl()

  @wrappers.Request.application
  def tags_route(self, request):
    index = self.index_impl()
    return http_util.Respond(request, index, 'application/json')

  @wrappers.Request.application
  def distributions_route(self, request):
    """Given a tag and single run, return an array of compressed histograms."""
    tag = request.args.get('tag')
    run = request.args.get('run')
    try:
      (body, mime_type) = self.distributions_impl(tag, run)
      code = 200
    except ValueError as e:
      (body, mime_type) = (str(e), 'text/plain')
      code = 400
    return http_util.Respond(request, body, mime_type, code=code)
