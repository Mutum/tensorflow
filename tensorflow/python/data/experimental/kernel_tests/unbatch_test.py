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
"""Tests for `tf.data.experimental.unbatch()`."""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import time

from absl.testing import parameterized
import numpy as np

from tensorflow.python.client import session
from tensorflow.python.data.experimental.ops import batching
from tensorflow.python.data.kernel_tests import test_base
from tensorflow.python.data.ops import dataset_ops
from tensorflow.python.framework import constant_op
from tensorflow.python.framework import dtypes
from tensorflow.python.framework import errors
from tensorflow.python.framework import ops
from tensorflow.python.framework import sparse_tensor
from tensorflow.python.ops import array_ops
from tensorflow.python.ops import math_ops
from tensorflow.python.ops import string_ops
from tensorflow.python.platform import test
from tensorflow.python.util import compat


class UnbatchTest(test_base.DatasetTestBase, parameterized.TestCase):

  def testUnbatchWithUnknownRankInput(self):
    placeholder = array_ops.placeholder(dtypes.int32)
    dataset = dataset_ops.Dataset.from_tensors(placeholder).apply(
        batching.unbatch())
    iterator = dataset.make_initializable_iterator()
    next_elem = iterator.get_next()

    with self.cached_session() as sess:
      sess.run(iterator.initializer, feed_dict={placeholder: [0, 1, 2, 3]})
      for i in range(4):
        self.assertEqual(i, self.evaluate(next_elem))
      with self.assertRaises(errors.OutOfRangeError):
        sess.run(next_elem)

  def testUnbatchScalarDataset(self):
    data = tuple([math_ops.range(10) for _ in range(3)])
    data = dataset_ops.Dataset.from_tensor_slices(data)
    expected_types = (dtypes.int32,) * 3
    data = data.batch(2)
    self.assertEqual(expected_types, data.output_types)
    data = data.apply(batching.unbatch())
    self.assertEqual(expected_types, data.output_types)

    iterator = data.make_one_shot_iterator()
    op = iterator.get_next()

    with self.cached_session() as sess:
      for i in range(10):
        self.assertEqual((i,) * 3, self.evaluate(op))

      with self.assertRaises(errors.OutOfRangeError):
        sess.run(op)

  def testUnbatchDatasetWithStrings(self):
    data = tuple([math_ops.range(10) for _ in range(3)])
    data = dataset_ops.Dataset.from_tensor_slices(data)
    data = data.map(lambda x, y, z: (x, string_ops.as_string(y), z))
    expected_types = (dtypes.int32, dtypes.string, dtypes.int32)
    data = data.batch(2)
    self.assertEqual(expected_types, data.output_types)
    data = data.apply(batching.unbatch())
    self.assertEqual(expected_types, data.output_types)

    iterator = data.make_one_shot_iterator()
    op = iterator.get_next()

    with self.cached_session() as sess:
      for i in range(10):
        self.assertEqual((i, compat.as_bytes(str(i)), i), self.evaluate(op))

      with self.assertRaises(errors.OutOfRangeError):
        sess.run(op)

  def testUnbatchDatasetWithSparseTensor(self):
    st = sparse_tensor.SparseTensorValue(
        indices=[[i, i] for i in range(10)],
        values=list(range(10)),
        dense_shape=[10, 10])
    data = dataset_ops.Dataset.from_tensors(st)
    data = data.apply(batching.unbatch())
    data = data.batch(5)
    data = data.apply(batching.unbatch())
    iterator = data.make_one_shot_iterator()
    next_element = iterator.get_next()

    with self.cached_session() as sess:
      for i in range(10):
        st_row = self.evaluate(next_element)
        self.assertEqual([i], st_row.indices)
        self.assertEqual([i], st_row.values)
        self.assertEqual([10], st_row.dense_shape)
      with self.assertRaises(errors.OutOfRangeError):
        sess.run(next_element)

  def testUnbatchDatasetWithDenseAndSparseTensor(self):
    st = sparse_tensor.SparseTensorValue(
        indices=[[i, i] for i in range(10)],
        values=list(range(10)),
        dense_shape=[10, 10])
    data = dataset_ops.Dataset.from_tensors((list(range(10)), st))
    data = data.apply(batching.unbatch())
    data = data.batch(5)
    data = data.apply(batching.unbatch())
    iterator = data.make_one_shot_iterator()
    next_element = iterator.get_next()

    with self.cached_session() as sess:
      for i in range(10):
        dense_elem, st_row = self.evaluate(next_element)
        self.assertEqual(i, dense_elem)
        self.assertEqual([i], st_row.indices)
        self.assertEqual([i], st_row.values)
        self.assertEqual([10], st_row.dense_shape)
      with self.assertRaises(errors.OutOfRangeError):
        sess.run(next_element)

  def testUnbatchSingleElementTupleDataset(self):
    data = tuple([(math_ops.range(10),) for _ in range(3)])
    data = dataset_ops.Dataset.from_tensor_slices(data)
    expected_types = ((dtypes.int32,),) * 3
    data = data.batch(2)
    self.assertEqual(expected_types, data.output_types)
    data = data.apply(batching.unbatch())
    self.assertEqual(expected_types, data.output_types)

    iterator = data.make_one_shot_iterator()
    op = iterator.get_next()

    with self.cached_session() as sess:
      for i in range(10):
        self.assertEqual(((i,),) * 3, self.evaluate(op))

      with self.assertRaises(errors.OutOfRangeError):
        sess.run(op)

  def testUnbatchMultiElementTupleDataset(self):
    data = tuple([(math_ops.range(10 * i, 10 * i + 10),
                   array_ops.fill([10], "hi")) for i in range(3)])
    data = dataset_ops.Dataset.from_tensor_slices(data)
    expected_types = ((dtypes.int32, dtypes.string),) * 3
    data = data.batch(2)
    self.assertAllEqual(expected_types, data.output_types)
    data = data.apply(batching.unbatch())
    self.assertAllEqual(expected_types, data.output_types)

    iterator = data.make_one_shot_iterator()
    op = iterator.get_next()

    with self.cached_session() as sess:
      for i in range(10):
        self.assertEqual(((i, b"hi"), (10 + i, b"hi"), (20 + i, b"hi")),
                         sess.run(op))

      with self.assertRaises(errors.OutOfRangeError):
        sess.run(op)

  def testUnbatchEmpty(self):
    data = dataset_ops.Dataset.from_tensors(
        (constant_op.constant([]), constant_op.constant([], shape=[0, 4]),
         constant_op.constant([], shape=[0, 4, 0])))
    data = data.apply(batching.unbatch())
    iterator = data.make_one_shot_iterator()
    next_element = iterator.get_next()

    with self.cached_session() as sess:
      with self.assertRaises(errors.OutOfRangeError):
        sess.run(next_element)

  def testUnbatchStaticShapeMismatch(self):
    data = dataset_ops.Dataset.from_tensors((np.arange(7), np.arange(8),
                                             np.arange(9)))
    with self.assertRaises(ValueError):
      data.apply(batching.unbatch())

  def testUnbatchDynamicShapeMismatch(self):
    ph1 = array_ops.placeholder(dtypes.int32, shape=[None])
    ph2 = array_ops.placeholder(dtypes.int32, shape=None)
    data = dataset_ops.Dataset.from_tensors((ph1, ph2))
    data = data.apply(batching.unbatch())
    iterator = data.make_initializable_iterator()
    next_element = iterator.get_next()

    with self.cached_session() as sess:
      # Mismatch in the 0th dimension.
      sess.run(
          iterator.initializer,
          feed_dict={
              ph1: np.arange(7).astype(np.int32),
              ph2: np.arange(8).astype(np.int32)
          })
      with self.assertRaises(errors.InvalidArgumentError):
        sess.run(next_element)

      # No 0th dimension (i.e. scalar value) for one component.
      sess.run(
          iterator.initializer,
          feed_dict={
              ph1: np.arange(7).astype(np.int32),
              ph2: 7
          })
      with self.assertRaises(errors.InvalidArgumentError):
        sess.run(next_element)


class UnbatchBenchmark(test.Benchmark):

  def benchmarkNativeUnbatch(self):
    batch_sizes = [1, 2, 5, 10, 20, 50]
    elems_per_trial = 10000
    with ops.Graph().as_default():
      dataset = dataset_ops.Dataset.from_tensors("element").repeat(None)
      batch_size_placeholder = array_ops.placeholder(dtypes.int64, shape=[])
      dataset = dataset.batch(batch_size_placeholder)
      dataset = dataset.apply(batching.unbatch())
      dataset = dataset.skip(elems_per_trial)
      iterator = dataset.make_initializable_iterator()
      next_element = iterator.get_next()

      with session.Session() as sess:
        for batch_size in batch_sizes:
          deltas = []
          for _ in range(5):
            sess.run(
                iterator.initializer,
                feed_dict={batch_size_placeholder: batch_size})
            start = time.time()
            sess.run(next_element.op)
            end = time.time()
            deltas.append((end - start) / elems_per_trial)

          median_wall_time = np.median(deltas)
          print("Unbatch (native) batch size: %d Median wall time per element:"
                " %f microseconds" % (batch_size, median_wall_time * 1e6))
          self.report_benchmark(
              iters=10000,
              wall_time=median_wall_time,
              name="benchmark_unbatch_dataset_native_batch_size_%d" %
              batch_size)

  # Include a benchmark of the previous `unbatch()` implementation that uses
  # a composition of more primitive ops. Eventually we'd hope to generate code
  # that is as good in both cases.
  def benchmarkOldUnbatchImplementation(self):
    batch_sizes = [1, 2, 5, 10, 20, 50]
    elems_per_trial = 10000
    with ops.Graph().as_default():
      dataset = dataset_ops.Dataset.from_tensors("element").repeat(None)
      batch_size_placeholder = array_ops.placeholder(dtypes.int64, shape=[])
      dataset = dataset.batch(batch_size_placeholder)
      dataset = dataset.flat_map(dataset_ops.Dataset.from_tensor_slices)
      dataset = dataset.skip(elems_per_trial)
      iterator = dataset.make_initializable_iterator()
      next_element = iterator.get_next()

      with session.Session() as sess:
        for batch_size in batch_sizes:
          deltas = []
          for _ in range(5):
            sess.run(
                iterator.initializer,
                feed_dict={batch_size_placeholder: batch_size})
            start = time.time()
            sess.run(next_element.op)
            end = time.time()
            deltas.append((end - start) / elems_per_trial)

          median_wall_time = np.median(deltas)
          print("Unbatch (unfused) batch size: %d Median wall time per element:"
                " %f microseconds" % (batch_size, median_wall_time * 1e6))
          self.report_benchmark(
              iters=10000,
              wall_time=median_wall_time,
              name="benchmark_unbatch_dataset_unfused_batch_size_%d" %
              batch_size)


if __name__ == "__main__":
  test.main()
