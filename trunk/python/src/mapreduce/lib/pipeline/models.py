#!/usr/bin/env python
#
# Copyright 2010 Google Inc.
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

"""Datastore models used by the Google App Engine Pipeline API."""

from google.appengine.ext import db
from google.appengine.ext import blobstore

# Relative imports
from mapreduce.lib import simplejson
import util


def truncate_value(value):
  """Shorten the given value, preserving dict structure."""
  if isinstance(value, dict):
    return dict((k, truncate_value(v)) for k, v in value.iteritems())
  else:
    return str(value)[:100]


class _PipelineRecord(db.Model):
  """Represents a Pipeline.

  Properties:
    class_path: Path of the Python class to use for this pipeline.
    root_pipeline: The root of the whole workflow; set to itself this pipeline
      is its own root.
    fanned_out: List of child _PipelineRecords that were started when this
      generator pipeline moved from WAITING to RUN.
    start_time: For pipelines with no start _BarrierRecord, when this pipeline
      was enqueued to run immediately.
    finalized_time: When this pipeline moved from WAITING or RUN to DONE.
    params: Serialized parameter dictionary.
    status: The current status of the pipeline.
    current_attempt: The current attempt (starting at 0) to run.
    max_attempts: Maximum number of attempts (starting at 0) to run.
    next_retry_time: ETA of the next retry attempt.
    retry_message: Why the last attempt failed; None or empty if no message.

  Root pipeline properties:
    is_root_pipeline: This is a root pipeline.
    abort_message: Why the whole pipeline was aborted; only saved on
      root pipelines.
    abort_requested: If an abort signal has been requested for this root
      pipeline; only saved on root pipelines
  """

  WAITING = 'waiting'
  RUN = 'run'
  DONE = 'done'
  ABORTED = 'aborted'

  class_path = db.StringProperty()
  root_pipeline = db.SelfReferenceProperty(
                      collection_name='child_pipelines_set')
  fanned_out = db.ListProperty(db.Key, indexed=False)
  start_time = db.DateTimeProperty(indexed=True)
  finalized_time = db.DateTimeProperty(indexed=False)

  # One of these two will be set, depending on the size of the params.
  params_text = db.TextProperty(name='params')
  params_blob = blobstore.BlobReferenceProperty(
      name='params_blob', indexed=False)

  status = db.StringProperty(choices=(WAITING, RUN, DONE, ABORTED),
                             default=WAITING)

  # Retry behavior
  current_attempt = db.IntegerProperty(default=0, indexed=False)
  max_attempts = db.IntegerProperty(default=1, indexed=False)
  next_retry_time = db.DateTimeProperty(indexed=False)
  retry_message = db.TextProperty()

  # Root pipeline properties
  is_root_pipeline = db.BooleanProperty()
  abort_message = db.TextProperty()
  abort_requested = db.BooleanProperty(indexed=False)

  @classmethod
  def kind(cls):
    return '_AE_Pipeline_Record'

  @property
  def params(self):
    """Returns the dictionary of parameters for this Pipeline."""
    if hasattr(self, '_params_decoded'):
      return self._params_decoded

    if self.params_blob is not None:
      value_encoded = self.params_blob.open().read()
    else:
      value_encoded = self.params_text

    value = simplejson.loads(value_encoded, cls=util.JsonDecoder)
    if isinstance(value, dict):
      kwargs = value.get('kwargs')
      if kwargs:
        adjusted_kwargs = {}
        for arg_key, arg_value in kwargs.iteritems():
          # Python only allows non-unicode strings as keyword arguments.
          adjusted_kwargs[str(arg_key)] = arg_value
        value['kwargs'] = adjusted_kwargs

    self._params_decoded = value
    return self._params_decoded

  def truncated_copy(self):
    """Create a lightweight copy of the pipeline with the args truncated."""
    return _LowMemoryPipelineRecord(self)


class _LowMemoryPipelineRecord(object):
  """Substitute for _PipelineRecord that takes up less space.

  This class has most of the attributes of _PipelineRecord (the ones we need to
  display the pipeline information in the UI), except that the pipeline
  arguments are truncated to save space.
  """
  def __init__(self, pipeline_record):
    self.class_path = pipeline_record.class_path
    # Skip root pipeline since ReferenceProperties are tricky.
    self.fanned_out = pipeline_record.fanned_out
    self.start_time = pipeline_record.start_time
    self.finalized_time = pipeline_record.finalized_time
    self.status = pipeline_record.status
    self.current_attempt = pipeline_record.current_attempt
    self.max_attempts = pipeline_record.max_attempts
    self.next_retry_time = pipeline_record.next_retry_time
    self.retry_message = pipeline_record.retry_message
    self.is_root_pipeline = pipeline_record.is_root_pipeline
    self.abort_message = pipeline_record.abort_message
    self.abort_requested = pipeline_record.abort_requested
    self.params = pipeline_record.params
    self.params['args'] = [truncate_value(v) for v in self.params['args']]
    self.params['kwargs'] = truncate_value(self.params['kwargs'])


class _SlotRecord(db.Model):
  """Represents an output slot.

  Properties:
    root_pipeline: The root of the workflow.
    filler: The pipeline that filled this slot.
    value: Serialized value for this slot.
    status: The current status of the slot.
    fill_time: When the slot was filled by the filler.
  """

  FILLED = 'filled'
  WAITING = 'waiting'

  root_pipeline = db.ReferenceProperty(_PipelineRecord)
  filler = db.ReferenceProperty(_PipelineRecord,
                                collection_name='filled_slots_set')

  # One of these two will be set, depending on the size of the value.
  value_text = db.TextProperty(name='value')
  value_blob = blobstore.BlobReferenceProperty(
      name='value_blob', indexed=False)

  status = db.StringProperty(choices=(FILLED, WAITING), default=WAITING,
                             indexed=False)
  fill_time = db.DateTimeProperty(indexed=False)

  @classmethod
  def kind(cls):
    return '_AE_Pipeline_Slot'

  @property
  def value(self):
    """Returns the value of this Slot."""
    if hasattr(self, '_value_decoded'):
      return self._value_decoded

    if self.value_blob is not None:
      encoded_value = self.value_blob.open().read()
    else:
      encoded_value = self.value_text

    self._value_decoded = simplejson.loads(encoded_value, cls=util.JsonDecoder)
    return self._value_decoded

  @property
  def filler_pipeline_key(self):
    return _SlotRecord.filler.get_value_for_datastore(self)

  def truncated_copy(self):
    """Return a lightweight copy of the slot with the value truncated."""
    return _LowMemorySlotRecord(self)


class _LowMemorySlotRecord(object):
  """Substitute for _SlotRecord that takes up less space.

  This class has most of the attributes of _SlotRecord (the ones we need to
  display the slot information in the UI), except that the slot value itself
  (if it exists) is truncated.
  """
  def __init__(self, slot_record):
    # Skip root pipeline since ReferenceProperties are tricky.
    self.filler_pipeline_key = slot_record.filler_pipeline_key
    self.status = slot_record.status
    # Getting the "value" property crashes if the slot isn't filled, so we need
    # this check.
    if self.status == _SlotRecord.FILLED:
      self.value = truncate_value(slot_record.value)
    self.fill_time = slot_record.fill_time


class _BarrierRecord(db.Model):
  """Represents a barrier.

  Properties:
    root_pipeline: The root of the workflow.
    target: The pipeline to run when the barrier fires.
    blocking_slots: The slots that must be filled before this barrier fires.
    trigger_time: When this barrier fired.
    status: The current status of the barrier.
  """

  # Barrier statuses
  FIRED = 'fired'
  WAITING = 'waiting'

  # Barrier trigger reasons (used as key names)
  START = 'start'
  FINALIZE = 'finalize'
  ABORT = 'abort'

  root_pipeline = db.ReferenceProperty(_PipelineRecord)
  target = db.ReferenceProperty(_PipelineRecord,
                                collection_name='called_barrier_set')
  blocking_slots = db.ListProperty(db.Key)
  trigger_time = db.DateTimeProperty(indexed=False)
  status = db.StringProperty(choices=(FIRED, WAITING), default=WAITING,
                             indexed=False)

  @classmethod
  def kind(cls):
    return '_AE_Pipeline_Barrier'


class _BarrierListener(db.Model):
  """Represents one instance of a barrier listening to a slot.

  Each entity of this kind is a child entity of a _SlotRecord and indicates
  that when the slot is filled, the barrier referenced by listening_barrier
  might need to be triggered. Since triggering a barrier is idempotent and
  we'll only trigger a barrier if all slots have actually been filled, it's ok
  for incorrect and duplicate BarrierListener entities to exist, as long as
  it's a superset of the actual set of records. This structure allows us to do
  a consistent read for listening barriers (using an ancestor query), and also
  allows us to safely add a batch of BarrierListeners (which will span multiple
  entity groups) outside of a transaction when adding or modifying a barrier.

  Properties:
    listening_barrier: The barrier to consider triggering when the parent slot
      is full.
  """
  listening_barrier = db.ReferenceProperty(_BarrierRecord)

  @classmethod
  def kind(cls):
    return '_AE_Pipeline_BarrierListener'

  @staticmethod
  def generate_subscription_entities(barrier, slot_keys):
    """Yield new entities to subscribe the given barrier to the given slots.

    The entities must be later stored. Note that it's unsafe to store all of
    these entities in the same transaction unless it is known that all given
    slots are in the same entity group.
    """
    for slot_key in slot_keys:
      yield _BarrierListener(
        parent=slot_key,
        listening_barrier=barrier)


class _StatusRecord(db.Model):
  """Represents the current status of a pipeline.

  Properties:
    message: The textual message to show.
    console_url: URL to iframe as the primary console for this pipeline.
    link_names: Human display names for status links.
    link_urls: URLs corresponding to human names for status links.
    status_time: When the status was written.
  """

  root_pipeline = db.ReferenceProperty(_PipelineRecord)
  message = db.TextProperty()
  console_url = db.TextProperty()
  link_names = db.ListProperty(db.Text, indexed=False)
  link_urls = db.ListProperty(db.Text, indexed=False)
  status_time = db.DateTimeProperty(indexed=False)

  @classmethod
  def kind(cls):
    return '_AE_Pipeline_Status'
